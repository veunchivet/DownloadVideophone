# Chivet-kh Video Grab 📱

App សម្រាប់ទូរស័ព្ទ៖ ដាក់ Link វីដេអូ (YouTube, TikTok, Facebook, Instagram, X ...) → ទាញវិដេអូ → រក្សាទុកក្នុងទូរស័ព្ទ

🔗 **App:** https://veunchivet.github.io/DownloadVideophone/

## ប្រើលើ Android (Termux)

1. ដំឡើង **Termux** ពី F-Droid
2. ដំឡើងកម្មវិធីដែលត្រូវការ:
   ```
   pkg update -y && pkg install -y python ffmpeg
   pip install -U yt-dlp
   termux-setup-storage
   ```
3. ដាក់ `server.py` ក្នុង Folder **Download** រួច Run:
   ```
   cd ~/storage/downloads && python server.py
   ```
4. បើក App ខាងលើក្នុង Chrome (ចុច **Allow** បើ Chrome សួរ) ឬបើក `http://127.0.0.1:8800`

វិដេអូនឹងរក្សាទុកក្នុង `Download/VideoGrab`

## ប្រើជាមួយ PC (WiFi តែមួយ)

```
pip install -U yt-dlp
python server.py
```
បើក Link ដែល server.py បង្ហាញ (ឧ. `http://192.168.x.x:8800`) នៅលើទូរស័ព្ទ

## ឯកសារ

| ឯកសារ | តួនាទី |
|---|---|
| `index.html` | App (UI) — Host លើ GitHub Pages |
| `server.py` | Server ទាញវិដេអូ (yt-dlp), API ដូច cobalt |

> សូមទាញតែវិដេអូដែលអ្នកមានសិទ្ធិប្រើប្រាស់ ឬជាវិដេអូរបស់ខ្លួនឯង។
