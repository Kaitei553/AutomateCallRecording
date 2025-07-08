from flask import Flask, request, jsonify
import openai
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os, json

# ✅ Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ✅ Initialize Firebase
firebase_creds = json.loads(os.getenv("Firebase_KEY"))
cred = credentials.Certificate(firebase_creds)
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
@app.route("/", methods=["GET"])
def home():
    return "✅ AutomateCallRecording API is running."


@app.route("/process", methods=["POST"])
def process_audio():
    # ✅ Get uploaded file
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No audio file uploaded"}), 400

    # ✅ Transcribe
    transcript = openai.audio.transcriptions.create(
        model="whisper-1",
        file=file,
        language="ja"
    )

    # ✅ Summarize
    summary_prompt = f"""
    以下の通話内容を要約してください。お客様の要望・課題・対応内容を3行以内でまとめてください：

    {transcript.text}
    """
    summary_response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "あなたは日本のカスタマーサポート担当者です。"},
            {"role": "user", "content": summary_prompt}
        ]
    )
    summary = summary_response.choices[0].message.content.strip()

    # ✅ Email
    email_prompt = f"""
    以下の要約に基づいて、お客様へのフォローアップメールを作成してください。
    ビジネス敬語を使って、丁寧で簡潔な文章でお願いします。

    要約:
    {summary}
    """
    email_response = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "あなたは丁寧な日本語メールを書くカスタマーサポート担当者です。"},
            {"role": "user", "content": email_prompt}
        ]
    )
    email_text = email_response.choices[0].message.content.strip()

    # ✅ Save to Firestore
    doc_ref = db.collection("calls").add({
        "transcript": transcript.text,
        "summary": summary,
        "email_draft": email_text,
        "created_at": firestore.SERVER_TIMESTAMP
    })

    return jsonify({
        "doc_id": doc_ref[1].id,
        "transcript": transcript.text,
        "summary": summary,
        "email_draft": email_text
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

