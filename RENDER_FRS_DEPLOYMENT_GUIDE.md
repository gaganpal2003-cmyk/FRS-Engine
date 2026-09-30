# How to Deploy Cairo FRS Engine on Render Cloud

This guide explains how to deploy your **Face Recognition API Engine** on [Render.com](https://render.com) so clients worldwide can access your API URL.

---

## 1. Prerequisites: Cloud Database (MySQL)

Render web service containers are stateless and run in the cloud, so your API engine needs to connect to an online cloud MySQL database rather than `localhost`.

### Free Cloud MySQL Options:
1. **[Aiven.io](https://aiven.io)** (Generous free tier MySQL)
2. **[Railway.app](https://railway.app)** (Instant 1-click MySQL)
3. **[Clever Cloud](https://www.clever-cloud.com)** or **[FreeSQLDatabase](https://www.freesqldatabase.com)**

Once you have your cloud MySQL credentials, you will put them into Render:
- `FRS_DB_HOST`
- `FRS_DB_USER`
- `FRS_DB_PASSWORD`
- `FRS_DB_NAME`

---

## 2. Push Code to GitHub

Open terminal in `e:\API_Engines\FRS_Gagan_Sept2026-main` and run:

```bash
git init
git add .
git commit -m "Add Face Recognition FastAPI with Render Docker deployment"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_FRS_REPO_NAME>.git
git push -u origin main
```

---

## 3. Deploy on Render (Step-by-Step)

1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Web Service**.
3. Select **Build and deploy from a Git repository** $\rightarrow$ Connect your repository.
4. Fill in the details:
   - **Name:** `cairo-frs-engine`
   - **Region:** Frankfurt (EU) or Singapore or Oregon (US)
   - **Runtime:** **Docker** (Render will automatically detect your `Dockerfile`)
   - **Instance Type:** Starter (Recommended for CV models: 1 CPU, 2 GB RAM) or Free
5. Scroll down to **Environment Variables** and add:

| Key | Value |
|---|---|
| `FRS_DB_HOST` | `<your-cloud-mysql-host>` |
| `FRS_DB_USER` | `<your-cloud-mysql-user>` |
| `FRS_DB_PASSWORD` | `<your-cloud-mysql-password>` |
| `FRS_DB_NAME` | `<your-cloud-mysql-db-name>` |
| `FRS_ADMIN_SECRET` | `cairo_frs_master_secret_2026` |
| `FRS_RECOGNITION_TOLERANCE` | `0.40` |

6. Click **Create Web Service**.

Render will now build your Docker container, install OpenCV and dlib, initialize your database, and launch your API.

---

## 4. Your Live Client API Endpoints

Once deployed, Render gives you a public HTTPS URL (e.g., `https://cairo-frs-engine.onrender.com`).

| Item | Production URL on Render |
|---|---|
| **Base API URL** | `https://cairo-frs-engine.onrender.com/api/v1` |
| **Recognize URL** | `https://cairo-frs-engine.onrender.com/api/v1/recognize` |
| **Enroll URL** | `https://cairo-frs-engine.onrender.com/api/v1/enroll` |
| **Verify URL** | `https://cairo-frs-engine.onrender.com/api/v1/verify` |
| **Interactive Docs** | `https://cairo-frs-engine.onrender.com/docs` |
| **Health Check** | `https://cairo-frs-engine.onrender.com/api/v1/health` |
