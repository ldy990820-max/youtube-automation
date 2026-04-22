import os
import json
import time
import shutil
import glob
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

# ==========================================
# 1. GENERATE PLAN VIA GEMINI API
# ==========================================
def generate_plan():
    print("[1/5] Generating plan.json via Gemini API...")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=gemini_api_key)
    # Using gemini-1.5-pro or gemini-pro.
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
    
    try:
        plan_data = json.loads(raw_text)
    except json.JSONDecodeError:
        print("Failed to decode JSON from Gemini. Raw text:", raw_text)
        raise
        
    with open("plan.json", "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    
    print("plan.json created successfully.")
    return plan_data

# ==========================================
# 2. SELENIUM SETUP & IMAGE GENERATION
# ==========================================
def get_chrome_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # For GitHub Actions
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Uncomment next line for headless mode in Github Actions
    chrome_options.add_argument("--headless=new")
    
    # Set default download directory
    prefs = {"download.default_directory" : os.path.abspath("assets/images")}
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def generate_images_flow_ai(plan_data):
    print("[2/5] Generating 9:16 Images on Flow AI...")
    os.makedirs("assets/images", exist_ok=True)
    
    driver = get_chrome_driver()
    try:
        driver.get("https://flow.ai") # Replace with actual Flow AI URL
        # TODO: Handle Login/Authentication (e.g. loading cookies from os.getenv("FLOW_AI_COOKIE"))
        
        for item in plan_data:
            print(f"Generating image for scene {item['scene']}...")
            prompt = item['image_prompt'] + ", 9:16 aspect ratio"
            
            # --- MOCK SELECTORS (Update with actual flow AI elements) ---
            # input_box = driver.find_element(By.XPATH, "//input[@placeholder='Enter prompt']")
            # input_box.send_keys(prompt)
            # generate_btn = driver.find_element(By.XPATH, "//button[text()='Generate']")
            # generate_btn.click()
            # WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//button[text()='Download']")))
            # download_btn = driver.find_element(By.XPATH, "//button[text()='Download']")
            # download_btn.click()
            # ------------------------------------------------------------
            
            time.sleep(5) # Simulating wait for download
            
            # Rename the latest downloaded file
            # This is a basic approach; actual implementation requires checking file timestamps
    finally:
        driver.quit()
    print("Images generated and saved to assets/images.")

# ==========================================
# 3. VIDEO GENERATION (veo 3.1-lite)
# ==========================================
def generate_videos_flow_ai(plan_data):
    print("[3/5] Generating 5s Videos on Flow AI (veo 3.1-lite)...")
    os.makedirs("assets/videos", exist_ok=True)
    
    # Needs a separate download folder strategy for videos
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    prefs = {"download.default_directory" : os.path.abspath("assets/videos")}
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        driver.get("https://flow.ai/video") # Replace with actual URL
        # TODO: Login logic
        
        images = sorted(glob.glob("assets/images/*.png") + glob.glob("assets/images/*.jpg"))
        for i, img_path in enumerate(images):
            print(f"Generating video for {img_path}...")
            
            # --- MOCK SELECTORS (Update with actual flow AI elements) ---
            # upload_input = driver.find_element(By.XPATH, "//input[@type='file']")
            # upload_input.send_keys(os.path.abspath(img_path))
            
            # model_select = driver.find_element(By.XPATH, "//select")
            # model_select.send_keys("veo 3.1-lite")
            
            # generate_btn = driver.find_element(By.XPATH, "//button[text()='Create Video']")
            # generate_btn.click()
            
            # WebDriverWait(driver, 120).until(EC.presence_of_element_located((By.XPATH, "//button[text()='Download Video']")))
            # download_btn = driver.find_element(By.XPATH, "//button[text()='Download Video']")
            # download_btn.click()
            # ------------------------------------------------------------
            
            time.sleep(5) # Simulating weight
    finally:
        driver.quit()
    print("Videos generated and saved to assets/videos.")

# ==========================================
# 4. FFMPEG MERGE
# ==========================================
def merge_videos():
    print("[4/5] Merging videos with FFmpeg (excluding TTS, adding BGM)...")
    videos = sorted(glob.glob("assets/videos/*.mp4"))
    if not videos:
        print("Warning: No videos found to merge. Skipping.")
        return
        
    with open("list.txt", "w", encoding="utf-8") as f:
        for vid in videos:
            f.write(f"file '{os.path.abspath(vid)}'\n")
            
    # Assuming bgm.mp3 exists in the root folder, or we download a generic one.
    bgm_path = "bgm.mp3" 
    
    if os.path.exists(bgm_path):
        # Concatenate and add BGM, truncate BGM to shortest (video length)
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-i", bgm_path, 
            "-c:v", "copy",
            "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", 
            "-shortest", "final_shorts.mp4"
        ]
    else:
        # Just concatenate
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-c", "copy", "final_shorts.mp4"
        ]
        print("Warning: bgm.mp3 not found. Merging without audio.")

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("final_shorts.mp4 created successfully.")
    except subprocess.CalledProcessError as e:
        print("FFmpeg error:", e.stderr.decode("utf-8", errors="ignore"))

# ==========================================
# 5. YOUTUBE UPLOAD (Data API v3)
# ==========================================
def upload_to_youtube():
    print("[5/5] Uploading to YouTube via Data API v3...")
    
    # The OAuth 2.0 components
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    
    if not all([client_id, client_secret, refresh_token]):
        print("YouTube credentials missing in environment variables. Skipping upload.")
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
            "title": "오늘의 건강 상식",
            "description": "요즘 건강상식 트랜드를 알려드립니다.",
            "tags": ["건강상식", "50대건강", "쇼츠", "shorts"],
            "categoryId": "22" # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload("final_shorts.mp4", chunksize=-1, resumable=True)
    )
    
    response = None
    print("Uploading file...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
            
    print(f"Upload Complete! Video ID: {response['id']}")

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    print("Starting Automated Shorts Workflow...")
    
    # Step 1: Create Plan
    plan = generate_plan()
    
    # Step 2: Generate Images (Mock integration)
    generate_images_flow_ai(plan)
    
    # Step 3: Generate Videos (Mock integration)
    generate_videos_flow_ai(plan)
    
    # Step 4: Map Videos
    merge_videos()
    
    # Step 5: Upload
    upload_to_youtube()
    
    print("Workflow Finished Successfully!")
