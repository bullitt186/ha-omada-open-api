"""Regression coverage for startup when the local Omada controller is offline."""

import ssl

import aiohttp

from custom_components.omada_open_api import _is_transient_connection_error
from custom_components.omada_open_api.api import OmadaApiAuthError, OmadaApiError


def _wrapped(cause: BaseException) -> OmadaApiError:
    error = OmadaApiError("Connection error: controller unavailable")
    error.__cause__ = cause
    return error


def test_refused_controller_connection_is_retriable():
    error = _wrapped(ConnectionRefusedError(111, "Connection refused"))
    assert _is_transient_connection_error(error)


def test_http_connection_failure_is_retriable():
    error = _wrapped(aiohttp.ServerDisconnectedError())
    assert _is_transient_connection_error(error)


def test_tls_certificate_failure_is_not_transient():
    error = _wrapped(ssl.SSLCertVerificationError("certificate verify failed"))
    assert not _is_transient_connection_error(error)


def test_application_error_is_not_transient():
    assert not _is_transient_connection_error(OmadaApiError("API error 404"))


def test_authentication_error_is_not_transient():
    assert not _is_transient_connection_error(OmadaApiAuthError("invalid credentials"))


def test_nested_transport_error_is_retriable():
    """Wrapped networking errors must survive multiple API layers."""
    inner = _wrapped(ConnectionRefusedError(111, "Connection refused"))
    outer = OmadaApiError("Unable to query sites")
    outer.__cause__ = inner
    assert _is_transient_connection_error(outer)


def test_unrelated_application_failure_is_not_misclassified():
    """Error text without a transport exception cause must not trigger retry."""
    assert not _is_transient_connection_error(
        OmadaApiError("Connection refused by account policy")
    )
