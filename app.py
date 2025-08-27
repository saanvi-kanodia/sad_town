import os
import cv2
import torch
from flask import Flask, request, render_template, send_from_directory
from PIL import Image
import google.generativeai as genai

# ========== CONFIG ==========
UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Gemini setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# Flask app
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER


# ---------- Helpers ----------

def generate_story_from_video(video_path):
    """
    Captions the video and generates a sad story using Gemini.
    """
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    # Step 1: Ask Gemini to caption the video
    caption_prompt = "Describe what is happening in this video in one sentence."
    caption_response = model.generate_content([caption_prompt, {"mime_type": "video/mp4", "data": video_bytes}])
    caption = caption_response.text.strip() if caption_response and caption_response.text else "A video was uploaded."

    # Step 2: Ask Gemini to create a sad story
    story_prompt = f"Write a short, sad story inspired by this description: {caption}"
    story_response = model.generate_content(story_prompt)
    story = story_response.text.strip() if story_response and story_response.text else "No story generated."

    return caption, story


def background_subtract(video_path, output_path):
    """
    Applies background subtraction and saves processed video.
    """
    capture = cv2.VideoCapture(video_path)
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    fps = capture.get(cv2.CAP_PROP_FPS)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    video_writer = cv2.VideoWriter(output_path, fourcc, fps, size, isColor=False)

    fgbg = cv2.createBackgroundSubtractorMOG2()

    while True:
        ret, frame = capture.read()
        if not ret:
            break
        fgmask = fgbg.apply(frame)
        video_writer.write(fgmask)

    capture.release()
    video_writer.release()


# ---------- Routes ----------

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "video" not in request.files:
            return "No video uploaded", 400
        file = request.files["video"]
        if file.filename == "":
            return "Empty filename", 400

        # Save uploaded video
        video_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(video_path)

        # Run Gemini: caption + story
        caption, story = generate_story_from_video(video_path)

        # Run background subtraction
        output_path = os.path.join(app.config["OUTPUT_FOLDER"], f"bgsub_{file.filename}")
        background_subtract(video_path, output_path)

        return f"""
        <h2>Video Uploaded!</h2>
        <p><b>Caption:</b> {caption}</p>
        <p><b>Sad Story:</b> {story}</p>
        <p><a href='/download/{os.path.basename(output_path)}'>Download Background-Subtracted Video</a></p>
        """

    return """
    <h1>Upload a Video</h1>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="video" accept="video/*">
        <input type="submit" value="Upload">
    </form>
    """


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(app.config["OUTPUT_FOLDER"], filename)


# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)