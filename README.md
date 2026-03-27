# Run Locally

## Backend

1. Open a terminal in the project root.
2. Run:

```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Keep that terminal running.

## Frontend

1. Open a new terminal in the project root.
2. Run:

```powershell
cd mobile
npm install
```

Metro is optional for a normal debug launch now because the Android debug APK bundles its own JavaScript. Start Metro only if you want live reload or dev-server debugging:

```powershell
npm start
```

This project keeps the React Native workspace on a short internal path to avoid Windows CMake/Ninja path-length build failures. The `mobile` folder in this project points to that workspace, so you can keep using the path below. If Android Studio ever has trouble following the link, open `C:\HGAI_mobile\android` directly instead.

3. Open Android Studio.
4. Click **Open**.
5. Open this folder:

```text
C:\Users\raash\Desktop\AI-based Heart Disease Prediction and Health Monitoring System\mobile\android
```

6. Wait for Gradle Sync to finish.
7. Open **Device Manager** in Android Studio and start your emulator.
8. In Android Studio, select the **app** run configuration.
9. Click **Run**.

# ai-health-check-app
