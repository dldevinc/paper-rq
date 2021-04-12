from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class Config(AppConfig):
    name = "paper_rq"
    label = "paper_rq"
    verbose_name = _("Django RQ")
