import openai
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import os

# ✅ Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ✅ Initialize Firebase
firebase_creds = json.loads(os.getenv("Firebase_KEY"))
cred = credentials.Certificate(firebase_creds)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ✅ Step 1: Transcribe audio
audio_path = "sample_voice.m4a"  # Replace with your actual file
with open(audio_path, "rb") as audio_file:
    transcript = openai.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="ja"
    )

print("📝 Transcript:\n", transcript.text)

# ✅ Step 2: Summarize with GPT
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
print("\n📋 Summary:\n", summary)

# ✅ Step 3: Generate follow-up email
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
print("\n📧 Email Draft:\n", email_text)

# ✅ Step 4: Save everything to Firestore
doc_ref = db.collection("calls").add({
    "recording_file": audio_path,
    "transcript": transcript.text,
    "summary": summary,
    "email_draft": email_text,
    "created_at": firestore.SERVER_TIMESTAMP
})
print(f"\n✅ Data saved to Firestore! Document ID: {doc_ref[1].id}")
