from typing import NamedTuple
from operator import attrgetter


class PseudoQuery(NamedTuple):
    select_related: bool
    order_by: list


class ListQuerySet:
    """
    Частичная эмуляция QuerySet, работающая со списком.
    """
    def __init__(self, model, data=None):
        self._wrapped = list(data) if data is not None else []
        self.model = model

    def __iter__(self):
        return iter(self._wrapped)

    def __len__(self):
        return len(self._wrapped)

    def __getitem__(self, item):
        return self._wrapped[item]

    def append(self, value):
        self._wrapped.append(value)

    @property
    def query(self):
        return PseudoQuery(
            select_related=False,
            order_by=[]
        )

    @property
    def verbose_name(self):
        return self.model._meta.verbose_name

    @property
    def verbose_name_plural(self):
        return self.model._meta.verbose_name_plural

    def _clone(self):
        return type(self)(self.model, self._wrapped.copy())

    def count(self):
        return len(self._wrapped)

    def all(self):
        return self

    def filter(self, *args, **kwargs):
        if "pk__in" in kwargs:
            # action checkbox support
            search_values = kwargs.pop("pk__in")
            return type(self)(self.model, [
                obj
                for obj in self._wrapped
                if attrgetter("pk")(obj) in search_values
            ])
        return self

    def order_by(self, *field_names):
        if not field_names:
            return self

        object_list = self._wrapped.copy()
        for fieldname in reversed(field_names):
            object_list = sorted(
                object_list,
                key=attrgetter(fieldname.lstrip("-")),
                reverse=fieldname.startswith("-")
            )

        return type(self)(self.model, object_list)

    def distinct(self, *field_names):
        return self

    def select_related(self, *fields):
        return self
