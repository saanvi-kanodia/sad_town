import os
import requests
import cv2
import time
from flask import Flask, render_template, request, Response
from transformers import pipeline
import dotenv
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['PROCESSED_FOLDER'] = 'static/processed'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

# Hugging Face API details
HF_API_TOKEN = os.getenv('HF_API_TOKEN')

HF_API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip2-opt-2.7b"

# Story generator (local)
story_generator = pipeline("text-generation", model="gpt2")

def generate_video_caption(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("Error: Could not read frame from video.")
            return "A mysterious scene with no visible details."

        frame_path = "temp_frame.jpg"
        cv2.imwrite(frame_path, frame)
        print(f"Saved frame to: {frame_path}")

        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        with open(frame_path, "rb") as f:
            data = f.read()

        print(f"Sending frame to Hugging Face API: {HF_API_URL}")
        response = requests.post(HF_API_URL, headers=headers, data=data, timeout=30)
        print(f"API Response Status: {response.status_code}")
        print(f"API Response Text: {response.text}")

        os.remove(frame_path)

        if response.status_code == 200:
            try:
                caption = response.json()[0]["generated_text"]
                print(f"Generated Caption: {caption}")
                return caption
            except Exception as e:
                print(f"JSON Parse Error: {str(e)}")
                return "A scene too complex for words."
        elif response.status_code == 429:
            print("API Rate Limit Exceeded. Waiting...")
            time.sleep(10)
            response = requests.post(HF_API_URL, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                caption = response.json()[0]["generated_text"]
                return caption
            else:
                return "A scene too busy for words. API rate limit exceeded."
        elif response.status_code == 503:
            print("API Unavailable. Retrying...")
            time.sleep(5)
            response = requests.post(HF_API_URL, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                caption = response.json()[0]["generated_text"]
                return caption
            else:
                return  API unavailable."
        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return f"API Error: {response.status_code}"
    except Exception as e:
        print(f"Caption Error: {str(e)}")
        return 0


def generate_sad_story(caption):
    prompt = f"Write a short, poetic, and sad story based on this scene: {caption}"
    story = story_generator(prompt, max_length=150, num_return_sequences=1)[0]['generated_text']
    return story

def process_video(input_path, output_path):
    print(f"Processing video: {input_path} -> {output_path}")
    capture = cv2.VideoCapture(input_path)
    if not capture.isOpened():
        print("Error: Could not open input video.")
        return False, 0

    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    out = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*'avc1'),
        fps,
        (frame_width, frame_height)
    )
    if not out.isOpened():
        print("Error: Could not open output video for writing.")
        return False, 0

    backSub = cv2.createBackgroundSubtractorMOG2()
    frame_count = 0

    for frame_count in range(total_frames):
        ret, frame = capture.read()
        if not ret:
            break
        fgMask = backSub.apply(frame)
        out.write(cv2.cvtColor(fgMask, cv2.COLOR_GRAY2BGR))
        progress = int((frame_count / total_frames) * 100)
        yield f"data: {progress}\n\n"  # Send progress update
        time.sleep(0.01)  # Simulate processing delay

    print(f"Processed {frame_count}/{total_frames} frames. Output saved to {output_path}.")
    capture.release()
    out.release()
    return True, frame_count

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return "No video uploaded."
    video = request.files['video']
    if video.filename == '':
        return "No selected video."

    input_path = os.path.join(app.config['UPLOAD_FOLDER'], 'input.mp4')
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], 'output.mp4')
    video.save(input_path)
    print(f"Saved uploaded video to: {input_path}")

    return render_template('processing.html')

@app.route('/process')
def process():
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], 'input.mp4')
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], 'output.mp4')

    def generate():
        success, _ = yield from process_video(input_path, output_path)
        if success:
            caption = generate_video_caption(input_path)
            story = generate_sad_story(caption)
            yield f"data: done\n\n"
            yield f"data: {caption}\n\n"
            yield f"data: {story}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/result')
def result():
    caption = request.args.get('caption', 'A mysterious scene.')
    story = request.args.get('story', 'Once upon a time...')
    return render_template('result.html', input_video='input.mp4', output_video='output.mp4', story=story, caption=caption)

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
