import apimodel


class Custom:
    def __init__(self, foo: int) -> None:
        self.foo = foo

    @classmethod
    def __validator__(cls, value: object):
        x = apimodel.parser.cast(int, value)
        return cls(x * 2)


def test_custom_validator():
    class Model(apimodel.APIModel):
        custom: Custom

    model = Model({"custom": 3})
    assert model.custom.foo == 6
