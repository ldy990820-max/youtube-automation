const fs = require('fs');
const http = require('http');
const https = require('https');
const path = require('path');
const { execSync } = require('child_process');
const googleTTS = require('google-tts-api');

const DIR = path.join(__dirname, 'assets', 'videos');
const PLAN_FILE = path.join(__dirname, 'plan.json');

async function downloadFile(url, dest) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(dest);
        const protocol = url.startsWith('https') ? https : http;
        protocol.get(url, (response) => {
            // handle redirects
            if (response.statusCode === 301 || response.statusCode === 302) {
                return resolve(downloadFile(response.headers.location, dest));
            }
            if (response.statusCode !== 200) {
                return reject(new Error(`Failed to get '${url}' (${response.statusCode})`));
            }
            response.pipe(file);
            file.on('finish', () => {
                file.close(resolve);
            });
        }).on('error', (err) => {
            fs.unlink(dest, () => {});
            reject(err);
        });
    });
}

const ffmpegPath = require('ffmpeg-static');

async function main() {
    try {
        console.log("Reading plan.json...");
        const planStr = fs.readFileSync(PLAN_FILE, 'utf-8');
        const plan = JSON.parse(planStr);

        // Download TTS
        console.log("Generating TTS files...");
        for (const scene of plan) {
            const num = scene.scene;
            const text = scene.script;
            console.log(`- Scene ${num}`);
            const base64 = await googleTTS.getAudioBase64(text, { lang: 'ko', slow: false });
            const buffer = Buffer.from(base64, 'base64');
            const dest = path.join(DIR, `scene${num}_tts.mp3`);
            fs.writeFileSync(dest, buffer);
        }

        // Download BGM
        console.log("Downloading BGM...");
        const bgmUrl = 'https://raw.githubusercontent.com/mdn/learning-area/master/html/multimedia-and-embedding/video-and-audio-content/viper.mp3';
        const bgmDest = path.join(DIR, 'bgm.mp3');
        if (!fs.existsSync(bgmDest) || fs.statSync(bgmDest).size < 1000) {
            await new Promise((resolve, reject) => {
                const file = fs.createWriteStream(bgmDest);
                https.get(bgmUrl, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } }, (response) => {
                    response.pipe(file);
                    file.on('finish', () => { file.close(resolve); });
                }).on('error', (err) => {
                    fs.unlink(bgmDest, () => {});
                    reject(err);
                });
            });
        }

        // FFmpeg Looping
        console.log("Merging video + audio for each scene...");
        let listContent = '';
        for (let i = 1; i <= 5; i++) {
            const vid = `scene${i}_video.mp4`;
            const aud = `scene${i}_tts.mp3`;
            const out = `scene${i}_full.mp4`;
            
            const cmd = `"${ffmpegPath}" -y -stream_loop -1 -i "${path.join(DIR, vid)}" -i "${path.join(DIR, aud)}" -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 23 -c:a copy -shortest "${path.join(DIR, out)}"`;
            console.log(`Executing: ${cmd}`);
            execSync(cmd, { stdio: 'inherit' });
            
            listContent += `file '${out}'\n`;
        }

        // Write list for concatenation
        console.log("Creating list.txt for concatenation...");
        const listFile = path.join(DIR, 'list.txt');
        fs.writeFileSync(listFile, listContent);

        // Concat All
        console.log("Concatenating all scenes...");
        const mergedOut = path.join(DIR, 'merged.mp4');
        const concatCmd = `"${ffmpegPath}" -y -f concat -safe 0 -i "${listFile}" -c copy "${mergedOut}"`;
        execSync(concatCmd, { stdio: 'inherit' });

        // Add BGM
        console.log("Adding BGM to the final video...");
        const finalOut = path.join(DIR, 'final_shorts.mp4');
        const addBgmCmd = `"${ffmpegPath}" -y -i "${mergedOut}" -stream_loop -1 -i "${bgmDest}" -filter_complex "[1:a]volume=0.15[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[a]" -map 0:v -map "[a]" -c:v copy -c:a aac "${finalOut}"`;
        execSync(addBgmCmd, { stdio: 'inherit' });

        console.log("Cleanup...");
        // Keep final_shorts.mp4, sceneX_video.mp4
        for (let i = 1; i <= 5; i++) {
            fs.unlinkSync(path.join(DIR, `scene${i}_tts.mp3`));
            fs.unlinkSync(path.join(DIR, `scene${i}_full.mp4`));
        }
        fs.unlinkSync(path.join(DIR, 'bgm.ogg'));
        fs.unlinkSync(listFile);
        fs.unlinkSync(mergedOut);

        console.log("DONE! Saved as assets/videos/final_shorts.mp4");

    } catch(err) {
        console.error("Error:", err);
        process.exit(1);
    }
}

main();
