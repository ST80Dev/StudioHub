def ui_preferences(request):
    """Rende disponibili in ogni template il tema e la densità UI dell'utente."""
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return {
            "current_theme": user.tema,
            "current_density": user.densita_ui,
        }
    return {"current_theme": "auto", "current_density": "compatta"}
