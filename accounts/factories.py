"""Factory per generare utenti demo.

Usate solo dal management command `seed_demo`. Non importare in runtime.
"""
from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from .models import AreaAziendale, UtenteStudio


class UtenteDemoFactory(DjangoModelFactory):
    """Utente interno dello studio, marcato is_demo=True.

    La password di default è `demo1234` per tutti: va bene solo per ambiente
    di test/dev. In prod produttiva non si crea mai un utente via questa factory.
    """

    class Meta:
        model = UtenteStudio
        django_get_or_create = ("username",)

    is_demo = True
    is_staff = False
    is_superuser = False
    first_name = factory.Faker("first_name", locale="it_IT")
    last_name = factory.Faker("last_name", locale="it_IT")
    username = factory.LazyAttribute(
        lambda o: f"{o.first_name}.{o.last_name}".lower().replace(" ", "")
    )
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.test")
    password = factory.PostGenerationMethodCall("set_password", "demo1234")

    @factory.post_generation
    def aree(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.aree.set(extracted)
            return
        # Di default assegna una o due aree casuali tra quelle esistenti.
        aree_attive = list(AreaAziendale.objects.filter(attivo=True))
        if not aree_attive:
            return
        import random

        k = min(len(aree_attive), random.choice([1, 1, 2]))
        self.aree.set(random.sample(aree_attive, k))
