try:
    from app.main import app
    print("✅ App Import erfolgreich")
except Exception as e:
    print(f"❌ Import Fehler: {e}")
    import traceback
    traceback.print_exc()
