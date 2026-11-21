# Chivet-kh Video Grab 📱

App សម្រាប់ទូរស័ព្ទ៖ ដាក់ Link វីដេអូ (YouTube, TikTok, Facebook, Instagram, X ...) → ទាញវិដេអូ → រក្សាទុកក្នុងទូរស័ព្ទ

🔗 **App:** https://veunchivet.github.io/DownloadVideophone/

## ☁️ ប្រើដូច savefrom (Server លើ Cloud — គ្មាន Termux)

App ភ្ជាប់ទៅ Server Cloud ដោយស្វ័យប្រវត្តិ: `https://downloadvideophone.onrender.com`

**ដាក់ Server ឡើង Render (ធ្វើម្ដងប៉ុណ្ណោះ, ឥតគិតថ្លៃ):**
1. ចូល https://render.com → Sign in ជាមួយ GitHub
2. **New → Blueprint** → ជ្រើស Repo `DownloadVideophone` → **Apply**
3. រង់ចាំ Build ~5 នាទី → Server រួចរាល់

> Render Free នឹង "ដេក" ពេលគ្មានអ្នកប្រើ 15 នាទី — ការទាញលើកដំបូងបន្ទាប់ពីដេកអាចចាំ ~1 នាទី។
> បើ Render ផ្ដល់ URL ផ្សេងពី `downloadvideophone.onrender.com` សូមប្ដូរ `DEFAULT_SERVER` ក្នុង `index.html`។

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
| `Dockerfile`, `render.yaml` | សម្រាប់ Deploy Server ទៅ Render |

> សូមទាញតែវិដេអូដែលអ្នកមានសិទ្ធិប្រើប្រាស់ ឬជាវិដេអូរបស់ខ្លួនឯង។
