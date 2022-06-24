import apimodel


class MyField(apimodel.fields.ModelFieldInfo):
    ...


class Base(apimodel.APIModel, field_cls=MyField):
    foo: int = 0


class Child(Base):
    bar: str = ""


class UnslottedBase(Base, slots=False):
    bar: str = ""


class UnslottedChild(UnslottedBase):
    random: int = 0


def test_inheritance():
    assert Child.__fields__.keys() == {"foo", "bar"}

    assert isinstance(Base.__fields__["foo"], MyField)
    assert isinstance(Child.__fields__["foo"], MyField)


def test_inheritance_slots():
    assert apimodel.utility.get_slots(Child()) == {"foo", "bar"}
    assert Child().__slots__ == ("bar",)
    # TODO: __dict__ still present

    assert hasattr(UnslottedBase(), "__dict__")
    assert hasattr(UnslottedChild(), "__dict__")
    assert apimodel.utility.get_slots(UnslottedBase()) == {"foo"}
