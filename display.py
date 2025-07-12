import openai
from flask import Flask, request, redirect
from dotenv import load_dotenv
import os
import requests
import json
import re
from datetime import datetime
from notion_client import Client

# Load .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Notion setup
notion = Client(auth=os.getenv("NOTION_TOKEN"))
notion_db_id = os.getenv("NOTION_DATABASE_ID")

# Flask App setup
app = Flask(__name__)
summaries = []

# 許可する拡張子
ALLOWED_EXTENSIONS = {'mp3', 'm4a', 'wav', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/", methods=["GET"])
def index():
    return '''
        <h2>Upload an Audio File</h2>
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="audio" accept=".mp3,.m4a,.wav,.webm" required>
            <button type="submit">Start Processing</button>
        </form>
        <br><a href="/records">📋 View Summaries</a>
    '''

@app.route("/upload", methods=["POST"])
def handle_upload():
    uploaded_file = request.files.get("audio")
    if not uploaded_file or not allowed_file(uploaded_file.filename):
        return "❌ Unsupported file format", 400

    local_filename = "uploaded_audio." + uploaded_file.filename.rsplit('.', 1)[1].lower()
    uploaded_file.save(local_filename)
    return process_audio(local_filename)

def process_audio(filepath):
    try:
        # Step 1: Whisper transcription
        with open(filepath, "rb") as audio:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio
            )
        print("📝 Transcript:\n", transcript.text)

        # Step 2: GPT summarization
        summary_prompt = f"""
        以下の通話を、相手の名前、お店の名前、そして電話先の業界を抽出して、三行でまとめてください。

        さらに、この通話には日程に関する予定が含まれていますか？含まれていれば、以下の形式でJSONとして出力してください：

        {{
          "title": "会議の概要タイトル",
          "start": "2025-07-09T14:00:00+09:00",
          "end": "2025-07-09T15:00:00+09:00"
        }}

        もし予定が含まれていなければ、`"none"` とだけ返答してください。
        もし予定が含まれていたら、アポインメント成功あので成功と、断られていたら失敗と最後に返答してください。

        以下、通話内容：

        {transcript.text}
        """

        summary_response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたはプロのアシスタントです。"},
                {"role": "user", "content": summary_prompt}
            ]
        )
        response_content = summary_response.choices[0].message.content.strip()
        print("\n📋 Summary:\n", response_content)

        # Step 3: Extract meeting info if available
        match = re.search(r'{[\s\S]*?}', response_content)
        if match:
            calendar_data = json.loads(match.group())
            meeting_title = calendar_data["title"]
            meeting_date = calendar_data["start"].split("T")[0]
        else:
            meeting_title = "会話記録"
            meeting_date = datetime.now().strftime("%Y-%m-%d")

        # Step 4: Determine appointment result
        lines = [line.strip() for line in response_content.split("\n") if line.strip()]
        if lines:
            result_line = lines[-1]
            if "成功" in result_line:
                appointment_result = "成功"
            elif "失敗" in result_line:
                appointment_result = "失敗"
            else:
                appointment_result = "不明"
        else:
            appointment_result = "不明"

        summary_text = "\n".join(lines[:3])

        # Step 5: Save to Notion
        notion.pages.create(
            parent={"database_id": notion_db_id},
            properties={
                "Consulting＆Interview": {
                    "title": [
                        {"text": {"content": meeting_title}}
                    ]
                },
                "Date": {
                    "date": {
                        "start": meeting_date
                    }
                },
                "Category": {
                    "multi_select": [
                        {"name": appointment_result}
                    ]
                },
                "Summary": {
                    "rich_text": [
                        {"text": {"content": summary_text}}
                    ]
                }
            }
        )
        summaries.append((meeting_title, meeting_date, summary_text, appointment_result))
        return redirect("/records")

    except Exception as e:
        print("❌ Error:", e)
        return f"❌ エラーが発生しました: {str(e)}"

@app.route("/records", methods=["GET"])
def show_records():
    html = "<h2>📋 summary</h2><ul>"
    if not summaries:
        html += "<li>no record。</li>"
    else:
        for title, date, summary, result in summaries[::-1]:
            html += f"<li><strong>{title}</strong>（{date}） - {result}<br><pre>{summary}</pre></li><hr>"
    html += "</ul><a href='/'>← back</a>"
    return html

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

