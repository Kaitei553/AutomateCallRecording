import openai
from flask import Flask, request, redirect
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
import os
import requests
import json
import re
from notion_client import Client
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

# Initialize APIs
notion = os.getenv("NOTION_TOKEN")
notion_db_id = os.getenv("NOTION_DATABASE_ID")
google_creds = json.loads(os.getenv("GOOGLE_CALENDAR_KEY"))

creds = service_account.Credentials.from_service_account_info(
    google_creds,
    scopes=['https://www.googleapis.com/auth/calendar']
)
calendar_service = build("calendar", "v3", credentials=creds)

# App setup
app = Flask(__name__)
summaries = []  # 📝 Store processed summaries

@app.route("/", methods=["GET"])
def index():
    return '''
        <h2>Upload the Audio</h2>
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="audio" accept=".mp3" required>
            <button type="submit">Start Working on it</button>
        </form>
        <br><a href="/records">📋 View Summaries</a>
    '''

@app.route("/upload", methods=["POST"])
def handle_upload():
    uploaded_file = request.files.get("audio")
    if not uploaded_file:
        return "No file uploaded", 400

    local_filename = "uploaded_audio.mp3"
    uploaded_file.save(local_filename)
    return process_audio(local_filename)

def process_audio(filepath):
    try:
        # ✅ Step 1: Transcribe with Whisper
        with open(filepath, "rb") as audio:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                language="ja"
            )
        print("📝 Transcript:\n", transcript.text)

        # ✅ Step 2: Summarize and extract schedule
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

        # ✅ Step 3: Google Calendar登録（必要なら）
        match = re.search(r'{[\s\S]*?}', response_content)
        if match:
            try:
                calendar_data = json.loads(match.group())
                event = {
                    "summary": calendar_data["title"],
                    "start": {
                        "dateTime": calendar_data["start"],
                        "timeZone": "Asia/Tokyo"
                    },
                    "end": {
                        "dateTime": calendar_data["end"],
                        "timeZone": "Asia/Tokyo"
                    }
                }
                calendar_service.events().insert(calendarId="primary", body=event).execute()
                print("📅 カレンダーイベントが作成されました！")
            except Exception as e:
                print("❌ イベント情報の解析に失敗しました:", e)
        else:
            print("📭 この通話には予定は含まれていません。")

        # ✅ Step 4: Notionに保存
        summary_lines = response_content.split("\n")
        summary_text = "\n".join(summary_lines[:3])

        if match:
            calendar_data = json.loads(match.group())
            meeting_title = calendar_data["title"]
            meeting_date = calendar_data["start"].split("T")[0]
            meeting_category = "Customer call"
        else:
            meeting_title = "会話記録"
            meeting_date = datetime.now().strftime("%Y-%m-%d")
            meeting_category = "Standup"

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

        print(f"📌 アポインメント結果: {appointment_result}")

        # Save to Notion
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
        print("✅ Notion page created successfully.")

        # ✅ Step 5: Save summary for web display
        summaries.append((meeting_title, meeting_date, summary_text, appointment_result))
        return redirect("/records")

    except Exception as e:
        print("❌ Error:", e)
        return f"❌ エラーが発生しました: {str(e)}"

@app.route("/records", methods=["GET"])
def show_records():
    html = "<h2>📋 zoom meeting summary</h2><ul>"
    if not summaries:
        html += "<li>no voice yet</li>"
    else:
        for title, date, summary, result in summaries[::-1]:
            html += f"<li><strong>{title}</strong>（{date}） - {result}<br><pre>{summary}</pre></li><hr>"
    html += "</ul><a href='/'>← back</a>"
    return html

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

