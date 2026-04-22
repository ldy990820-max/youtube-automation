import os
import json
import time
import shutil
import glob
from datetime import datetime
from pathlib import Path
import subprocess

import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# GCS imports
from google.cloud import storage

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
TODAY_STR = datetime.utcnow().strftime("%Y-%m-%d")

# ==========================================
# GCS HELPER
# ==========================================
def upload_to_gcs(local_path, remote_path):
    if not BUCKET_NAME:
        print("Warning: GCS_BUCKET_NAME is not set, skipping upload.")
        return
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(remote_path)
    blob.upload_from_filename(local_path)
    print(f"Uploaded {local_path} to gs://{BUCKET_NAME}/{remote_path}")

def download_from_gcs(remote_path, local_path):
    if not BUCKET_NAME:
        print("Warning: GCS_BUCKET_NAME is not set, skipping download.")
        return False
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(remote_path)
    if blob.exists():
        blob.download_to_filename(local_path)
        print(f"Downloaded gs://{BUCKET_NAME}/{remote_path} to {local_path}")
        return True
    else:
        print(f"Warning: Remote file gs://{BUCKET_NAME}/{remote_path} not found.")
        return False

# ==========================================
# 1. GENERATE PLAN VIA GEMINI API
# ==========================================
def generate_plan():
    print("[1/5] Generating plan.json via Gemini API...")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    prompt = """
    최신 유튜브 트렌드를 분석해서 50대의 건강 상식에 대한 1분 쇼츠 대본을 5개의 장면(scene)으로 작성해주세요. 
    대본의 각 장면별로 어울리는 이미지 생성 프롬프트(영문)를 포함해서 JSON 형식으로 출력해주세요.
    반드시 마크다운 코드블록이나 불필요한 텍스트 없이 순수 JSON 배열만 반환해주세요.
    형식 예시:
    [
      {"scene": 1, "script": "...", "image_prompt": "..."},
      {"scene": 2, "script": "...", "image_prompt": "..."}
    ]
    """
    
    response = model.generate_content(prompt)
    raw_text = response.text.replace("```json", "").replace("```", "").strip()
    
    plan_data = json.loads(raw_text)
    
    # Store locally temporarily, then upload to GCS, then remove locally
    local_plan = "plan.json"
    with open(local_plan, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    upload_to_gcs(local_plan, f"{TODAY_STR}/plan.json")
    os.remove(local_plan) # Clean up local
    
    print("plan.json generated and uploaded successfully.")
    return plan_data

# ==========================================
# 2. SELENIUM SETUP & IMAGE GENERATION
# ==========================================
def get_chrome_driver(download_dir):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--headless=new")
    
    prefs = {"download.default_directory": os.path.abspath(download_dir)}
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def generate_images_flow_ai(plan_data):
    print("[2/5] Generating 9:16 Images on Flow AI...")
    local_dir = "temp_images"
    os.makedirs(local_dir, exist_ok=True)
    
    driver = get_chrome_driver(local_dir)
    try:
        driver.get("https://flow.ai") 
        # TODO: Handle Login/Authentication
        
        for item in plan_data:
            print(f"Generating image for scene {item['scene']}...")
            prompt = item['image_prompt'] + ", 9:16 aspect ratio"
            
            # --- MOCK SELECTORS ---
            time.sleep(5) # Simulating wait for download
            
            downloaded_files = glob.glob(f"{local_dir}/*")
            if downloaded_files:
                latest_file = max(downloaded_files, key=os.path.getctime)
                remote_path = f"{TODAY_STR}/images/scene_{item['scene']}{Path(latest_file).suffix}"
                upload_to_gcs(latest_file, remote_path)
                os.remove(latest_file)
    finally:
        driver.quit()
    
    # We remove the physical directory afterwards
    shutil.rmtree(local_dir, ignore_errors=True)
    print("Images generation step finished (assets pushed to GCS).")

# ==========================================
# 3. VIDEO GENERATION (veo 3.1-lite)
# ==========================================
def generate_videos_flow_ai(plan_data):
    print("[3/5] Generating 5s Videos on Flow AI (veo 3.1-lite)...")
    local_vid_dir = "temp_videos"
    local_img_dir = "temp_images_downloads"
    os.makedirs(local_vid_dir, exist_ok=True)
    os.makedirs(local_img_dir, exist_ok=True)
    
    driver = get_chrome_driver(local_vid_dir)
    try:
        driver.get("https://flow.ai/video")
        
        for item in plan_data:
            scene = item['scene']
            # Fetch the image to use as a base
            remote_img_path = f"{TODAY_STR}/images/scene_{scene}.png"
            local_img_path = f"{local_img_dir}/scene_{scene}.png"
            # Attempt to download assuming .png
            if download_from_gcs(remote_img_path, local_img_path):
                print(f"Generating video for {local_img_path}...")
                
                # --- MOCK SELECTORS ---
                time.sleep(5)
                
                downloaded_files = glob.glob(f"{local_vid_dir}/*")
                if downloaded_files:
                    latest_file = max(downloaded_files, key=os.path.getctime)
                    remote_vid_path = f"{TODAY_STR}/videos/scene_{scene}.mp4"
                    upload_to_gcs(latest_file, remote_vid_path)
                    os.remove(latest_file)
    finally:
        driver.quit()
        
    shutil.rmtree(local_img_dir, ignore_errors=True)
    shutil.rmtree(local_vid_dir, ignore_errors=True)
    print("Videos generation step finished (assets pushed to GCS).")

# ==========================================
# 4. FFMPEG MERGE
# ==========================================
def merge_videos():
    print("[4/5] Merging videos with FFmpeg...")
    os.makedirs("merge_workspace", exist_ok=True)
    
    # Download videos from GCS
    if BUCKET_NAME:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=f"{TODAY_STR}/videos/"))
        for blob in sorted(blobs, key=lambda b: b.name):
            if blob.name.endswith(".mp4"):
                local_path = os.path.join("merge_workspace", Path(blob.name).name)
                blob.download_to_filename(local_path)
    
    videos = sorted(glob.glob("merge_workspace/*.mp4"))
    if not videos:
        print("Warning: No videos fetched from GCS. Skipping merge.")
        return
        
    with open("list.txt", "w", encoding="utf-8") as f:
        for vid in videos:
            f.write(f"file '{os.path.abspath(vid)}'\n")
            
    bgm_path = "bgm.mp3" 
    final_mp4 = "final_shorts.mp4"
    if os.path.exists(bgm_path):
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-i", bgm_path, "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", 
            "-shortest", final_mp4
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-c", "copy", final_mp4
        ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("final_shorts.mp4 created locally.")
        upload_to_gcs(final_mp4, f"{TODAY_STR}/final_shorts.mp4")
    except subprocess.CalledProcessError as e:
        print("FFmpeg error:", e.stderr.decode("utf-8", errors="ignore"))
    finally:
        shutil.rmtree("merge_workspace", ignore_errors=True)
        if os.path.exists("list.txt"): os.remove("list.txt")

# ==========================================
# 5. YOUTUBE UPLOAD
# ==========================================
def upload_to_youtube():
    print("[5/5] Uploading to YouTube via Data API v3...")
    
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    
    # We use the final_mp4 left over locally from Step 4.
    # If starting from scratch, download_from_gcs(f"{TODAY_STR}/final_shorts.mp4", "final_shorts.mp4")
    final_mp4 = "final_shorts.mp4"
    if not os.path.exists(final_mp4):
        if not download_from_gcs(f"{TODAY_STR}/final_shorts.mp4", final_mp4):
            print("Cannot find final_shorts.mp4 on GCS or disk.")
            return

    if not all([client_id, client_secret, refresh_token]):
        print("YouTube credentials missing. Skipping upload.")
        return
        
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    
    youtube = build("youtube", "v3", credentials=credentials)
    
    body = {
        "snippet": {
            "title": f"오늘의 건강 상식 ({TODAY_STR})",
            "description": "요즘 건강상식 트랜드를 알려드립니다.",
            "tags": ["건강상식", "50대건강", "쇼츠", "shorts"],
            "categoryId": "22"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(final_mp4, chunksize=-1, resumable=True)
    )
    
    response = None
    print("Uploading file...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
            
    print(f"Upload Complete! Video ID: {response['id']}")
    os.remove(final_mp4) # Pure cleanup

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    print("Starting Cloud-based Automated Shorts Workflow...")
    plan = generate_plan()
    generate_images_flow_ai(plan)
    generate_videos_flow_ai(plan)
    merge_videos()
    upload_to_youtube()
    print("Workflow Finished Successfully!")
