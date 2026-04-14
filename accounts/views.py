from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Tema


@login_required
def preferenze(request):
    if request.method == "POST":
        user = request.user
        user.tema = request.POST.get("tema", user.tema)
        user.densita_ui = request.POST.get("densita_ui", user.densita_ui)
        user.save(update_fields=["tema", "densita_ui"])
        return redirect("accounts:preferenze")
    return render(request, "accounts/preferenze.html", {"temi": Tema.choices})


@login_required
@require_POST
def cambia_tema(request):
    """Endpoint HTMX/POST per toggle rapido del tema dalla topbar."""
    nuovo = request.POST.get("tema")
    if nuovo in dict(Tema.choices):
        request.user.tema = nuovo
        request.user.save(update_fields=["tema"])
    if request.htmx:
        return HttpResponse(status=204, headers={"HX-Refresh": "true"})
    return redirect(request.META.get("HTTP_REFERER", "/"))
