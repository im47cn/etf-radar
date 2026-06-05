from src.providers.base import EtfDataProvider, ProviderError, EmptyDataError


def test_provider_error_is_exception() -> None:
    assert issubclass(ProviderError, Exception)
    assert issubclass(EmptyDataError, ProviderError)


def test_provider_protocol_callable() -> None:
    assert hasattr(EtfDataProvider, 'fetch_ohlc')
