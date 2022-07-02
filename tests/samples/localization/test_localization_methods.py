import datetime
import typing

import pytest

import apimodel


def localize_datetime(dt: datetime.datetime, locale: str) -> str:
    if locale == "en-us":
        # I hate this oh god
        return dt.strftime("%m/%d/%Y %I:%M:%S %p")
    else:
        return dt.strftime("%d. %m. %Y %H:%M:%S")


class User(apimodel.LocalizedAPIModel):
    username: str = apimodel.Field(name="name")
    password: str

    @property
    def email(self) -> str:
        domain = self.locale.split("-")[-1] if self.locale else "net"
        return self.username + "@example." + domain


class Model(apimodel.LocalizedAPIModel):
    users: typing.Sequence[User]

    number: int
    string: str
    color: int
    timestamp: datetime.datetime = apimodel.Field(localizator=localize_datetime)


Model.i18n.update(
    {
        "en-gb": {
            "color": "colour",
        },
        "de-de": {
            "number": "nummer",
            "string": "string",
            "color": "farbe",
            "timestamp": "zeitstempel",
            "users": "benutzer",
            "username": "benutzername",
            "password": "passwort",
        },
        "fr-fr": {
            "number": "nombre",
            "string": "chaine",
            "color": "couleur",
            "timestamp": "horodatage",
            "users": "utilisateurs",
            "username": "nom d'utilisateur",
            "password": "mot de passe",
        },
    }
)


@pytest.fixture()
def data() -> typing.Mapping[str, object]:
    return {
        "number": 0,
        "string": "foo",
        "color": 0xFFFFFF,
        "timestamp": datetime.datetime(2020, 1, 1, 12, 0, 0),
        "users": [{"name": "foo", "password": "bar"}, {"name": "baz", "password": "qux"}],
    }


def test_as_dict(data: typing.Mapping[str, object]) -> None:
    model = Model(data)
    assert model.as_dict() == {
        "number": 0,
        "string": "foo",
        "color": 0xFFFFFF,
        "timestamp": datetime.datetime(2020, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc),
        "users": [
            {"username": "foo", "password": "bar", "email": "foo@example.net"},
            {"username": "baz", "password": "qux", "email": "baz@example.net"},
        ],
    }
    assert "colour" in model.as_dict(locale="en-gb")

    fr_model = Model(data, locale="fr-fr")
    assert fr_model.as_dict() == {
        "nombre": 0,
        "chaine": "foo",
        "couleur": 0xFFFFFF,
        "horodatage": "01. 01. 2020 12:00:00",
        "utilisateurs": [
            {"nom d'utilisateur": "foo", "mot de passe": "bar", "email": "foo@example.fr"},
            {"nom d'utilisateur": "baz", "mot de passe": "qux", "email": "baz@example.fr"},
        ],
    }
