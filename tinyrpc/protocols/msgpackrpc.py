#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .. import (
    RPCError,
    RPCErrorResponse,
    RPCProtocol,
    RPCRequest,
    RPCResponse,
    InvalidRequestError,
    MethodNotFoundError,
    InvalidReplyError,
)

import msgpack
import six

from typing import Any, Dict, List, Optional, Tuple, Union


class FixedErrorMessageMixin(object):
    def __init__(self, *args, **kwargs):
        if not args:
            args = [self.message]

        self.request_id = kwargs.pop("request_id", None)
        super(FixedErrorMessageMixin, self).__init__(*args, **kwargs)

    def error_respond(self):
        response = MSGPACKRPCErrorResponse()

        response.error = self.message
        response.unique_id = self.request_id
        response._msgpackrpc_error_code = self.msgpackrpc_error_code
        return response


class MSGPACKRPCParseError(FixedErrorMessageMixin, InvalidRequestError):
    msgpackrpc_error_code = -32700
    message = "Parse error"


class MSGPACKRPCInvalidRequestError(FixedErrorMessageMixin, InvalidRequestError):
    msgpackrpc_error_code = -32600
    message = "Invalid request"


class MSGPACKRPCMethodNotFoundError(FixedErrorMessageMixin, MethodNotFoundError):
    msgpackrpc_error_code = -32601
    message = "Method not found"


class MSGPACKRPCInvalidParamsError(FixedErrorMessageMixin, InvalidRequestError):
    msgpackrpc_error_code = -32602
    message = "Invalid params"


class MSGPACKRPCInternalError(FixedErrorMessageMixin, InvalidRequestError):
    msgpackrpc_error_code = -32603
    message = "Internal error"


class MSGPACKRPCServerError(FixedErrorMessageMixin, InvalidRequestError):
    msgpackrpc_error_code = -32000
    message = ""


class MSGPACKRPCError(FixedErrorMessageMixin, RPCError):
    """Reconstructs (to some extend) the server-side exception.

    The client creates this exception by providing it with the ``error``
    attribute of the MSGPACK error response object returned by the server.

    :param error: This tuple contains the error specification: the numeric error
        code and the error description.
    """

    def __init__(
        self, error: Union["MSGPACKRPCErrorResponse", Tuple[int, str]]
    ) -> None:
        if isinstance(error, MSGPACKRPCErrorResponse):
            super().__init__(error.error)
            self._msgpackrpc_error_code = error._msgpackrpc_error_code
        else:
            super().__init__()
            self._msgpackrpc_error_code, self.message = error


class MSGPACKRPCSuccessResponse(RPCResponse):
    def _to_list(self):
        return [1, self.unique_id, None, self.result]

    def serialize(self):
        return msgpack.packb(self._to_list(), use_bin_type=True)


class MSGPACKRPCErrorResponse(RPCErrorResponse):
    def _to_list(self):
        return [1, self.unique_id, [self._msgpackrpc_error_code, str(self.error)], None]

    def serialize(self):
        return msgpack.packb(self._to_list(), use_bin_type=True)


def _get_code_and_message(error):
    assert isinstance(error, (Exception, six.string_types))
    if isinstance(error, Exception):
        if hasattr(error, "msgpackrpc_error_code"):
            code = error.msgpackrpc_error_code
            msg = str(error)
        elif isinstance(error, InvalidRequestError):
            code = MSGPACKRPCInvalidRequestError.msgpackrpc_error_code
            msg = MSGPACKRPCInvalidRequestError.message
        elif isinstance(error, MethodNotFoundError):
            code = MSGPACKRPCMethodNotFoundError.msgpackrpc_error_code
            msg = MSGPACKRPCMethodNotFoundError.message
        else:
            # allow exception message to propagate
            code = MSGPACKRPCServerError.msgpackrpc_error_code
            msg = str(error)
    else:
        code = -32000
        msg = error

    return code, msg


class MSGPACKRPCRequest(RPCRequest):
    """Defines a MSGPACK-RPC request."""

    def __init__(self):
        super().__init__()
        self.one_way = False
        """Request or Notification.

        :type: bool

        This flag indicates if the client expects to receive a reply (request: ``one_way = False``)
        or not (notification: ``one_way = True``).

        Note that it is possible for the server to return an error response.
        For example if the request becomes unreadable and the server is not able to determine that it is
        in fact a notification an error should be returned. However, once the server had verified that the
        request is a notification no reply (not even an error) should be returned.
        """

        self.unique_id = None
        """Correlation ID used to match request and response.

        :type: int

        Generated by the client, the server copies it from request to corresponding response.
        """

        self.method = None
        """The name of the RPC function to be called.

        :type: str

        The :py:attr:`method` attribute uses the name of the function as it is known by the public.
        The :py:class:`~tinyrpc.dispatch.RPCDispatcher` allows the use of public aliases in the
        ``@public`` decorators.
        These are the names used in the :py:attr:`method` attribute.
        """

        self.args = []
        """The positional arguments of the method call.

        :type: list

        The contents of this list are the positional parameters for the :py:attr:`method` called.
        It is eventually called as ``method(*args)``.
        """

    def error_respond(
        self, error: Union[Exception, str]
    ) -> Optional["MSGPACKRPCErrorResponse"]:
        """Create an error response to this request.

        When processing the request produces an error condition this method can be used to
        create the error response object.

        :param error: Specifies what error occurred.
        :type error: Exception or str
        :returns: An error response object that can be serialized and sent to the client.
        :rtype: ;py:class:`MSGPACKRPCErrorResponse`
        """
        if not self.unique_id:
            return None

        response = MSGPACKRPCErrorResponse()
        response.unique_id = None if self.one_way else self.unique_id

        code, msg = _get_code_and_message(error)

        response.error = msg
        response._msgpackrpc_error_code = code
        return response

    def respond(self, result: Any) -> Optional["MSGPACKRPCSuccessResponse"]:
        """Create a response to this request.

        When processing the request completed successfully this method can be used to
        create a response object.

        :param result: The result of the invoked method.
        :type result: Anything that can be encoded by MSGPACK.
        :returns: A response object that can be serialized and sent to the client.
        :rtype: :py:class:`MSGPACKRPCSuccessResponse`
        """
        if self.one_way or self.unique_id is None:
            return None

        response = MSGPACKRPCSuccessResponse()

        response.result = result
        response.unique_id = self.unique_id

        return response

    def _to_list(self):
        if self.one_way or self.unique_id is None:
            return [2, self.method, self.args if self.args is not None else []]
        else:
            return [
                0,
                self.unique_id,
                self.method,
                self.args if self.args is not None else [],
            ]

    def serialize(self) -> bytes:
        return msgpack.packb(self._to_list(), use_bin_type=True)


class MSGPACKRPCProtocol(RPCProtocol):
    """MSGPACKRPC protocol implementation."""

    def __init__(self, *args, **kwargs):
        super(MSGPACKRPCProtocol, self).__init__(*args, **kwargs)
        self._id_counter = 0

    def _get_unique_id(self):
        self._id_counter += 1
        return self._id_counter

    def request_factory(self) -> "MSGPACKRPCRequest":
        """Factory for request objects.

        Allows derived classes to use requests derived from :py:class:`MSGPACKRPCRequest`.

        :rtype: :py:class:`MSGPACKRPCRequest`
        """
        return MSGPACKRPCRequest()

    def create_request(
        self,
        method: str,
        args: List[Any] = None,
        kwargs: Dict[str, Any] = None,
        one_way: bool = False,
    ) -> "MSGPACKRPCRequest":
        """Creates a new :py:class:`MSGPACKRPCRequest` object.

        Called by the client when constructing a request.
        MSGPACK-RPC allows only the ``args`` argument to be set; keyword
        arguments are not supported.

        :param str method: The method name to invoke.
        :param list args: The positional arguments to call the method with.
        :param dict kwargs: The keyword arguments to call the method with; must
            be ``None`` as the protocol does not support keyword arguments.
        :param bool one_way: The request is an update, i.e. it does not expect a reply.
        :return: A new request instance
        :rtype: :py:class:`MSGPACKRPCRequest`
        :raises InvalidRequestError: when ``kwargs`` is defined.
        """
        if kwargs:
            raise MSGPACKRPCInvalidRequestError("Does not support kwargs")

        request = self.request_factory()
        request.one_way = one_way

        if not one_way:
            request.unique_id = self._get_unique_id()

        request.method = method
        request.args = list(args) if args is not None else []
        request.kwargs = None

        return request

    def parse_reply(
        self, data: bytes
    ) -> Union["MSGPACKRPCSuccessResponse", "MSGPACKRPCErrorResponse"]:
        """De-serializes and validates a response.

        Called by the client to reconstruct the serialized :py:class:`MSGPACKRPCResponse`.

        :param bytes data: The data stream received by the transport layer containing the
            serialized response.
        :return: A reconstructed response.
        :rtype: :py:class:`MSGPACKRPCSuccessResponse` or :py:class:`MSGPACKRPCErrorResponse`
        :raises InvalidReplyError: if the response is not valid MSGPACK or does not conform
            to the standard.
        """
        try:
            rep = msgpack.unpackb(data, raw=False)
        except Exception as e:
            raise InvalidReplyError(e)

        if len(rep) != 4:
            raise InvalidReplyError("MSGPACKRPC spec requires reply of length 4")

        if rep[0] != 1:
            raise InvalidReplyError("Invalid MSGPACK message type")

        if not isinstance(rep[1], int):
            raise InvalidReplyError("Invalid or missing message ID in response")

        if rep[2] is not None and rep[3] is not None:
            raise InvalidReplyError("Reply must contain only one of result and error.")

        if rep[2] is not None:
            response = MSGPACKRPCErrorResponse()
            if isinstance(rep[2], list) and len(rep[2]) == 2:
                code, message = rep[2]
                if isinstance(code, int) and isinstance(message, str):
                    response.error = str(message)
                    response._msgpackrpc_error_code = int(code)
                else:
                    response.error = rep[2]
                    response._msgpackrpc_error_code = None
            else:
                response.error = rep[2]
                response._msgpackrpc_error_code = None
        else:
            response = MSGPACKRPCSuccessResponse()
            response.result = rep[3]

        response.unique_id = rep[1]

        return response

    def parse_request(self, data: bytes) -> "MSGPACKRPCRequest":
        """De-serializes and validates a request.

        Called by the server to reconstruct the serialized :py:class:`MSGPACKRPCRequest`.

        :param bytes data: The data stream received by the transport layer containing the
            serialized request.
        :return: A reconstructed request.
        :rtype: :py:class:`MSGPACKRPCRequest`
        :raises MSGPACKRPCParseError: if the ``data`` cannot be parsed as valid MSGPACK.
        :raises MSGPACKRPCInvalidRequestError: if the request does not comply with the standard.
        """
        try:
            req = msgpack.unpackb(data, raw=False)
        except Exception:
            raise MSGPACKRPCParseError()

        if not isinstance(req, list):
            raise MSGPACKRPCInvalidRequestError()

        if len(req) < 2:
            raise MSGPACKRPCInvalidRequestError()

        if req[0] == 0:
            # MSGPACK request
            request_id = req[1]
            if not isinstance(request_id, int):
                raise MSGPACKRPCInvalidRequestError()

            if len(req) == 4:
                return self._parse_request(req)
            else:
                raise MSGPACKRPCInvalidRequestError(request_id=request_id)
        elif req[0] == 2:
            # MSGPACK notification
            if len(req) == 3:
                return self._parse_notification(req)
            else:
                raise MSGPACKRPCInvalidRequestError()
        else:
            raise MSGPACKRPCInvalidRequestError()

    def _parse_notification(self, req):
        if not isinstance(req[1], six.string_types):
            raise MSGPACKRPCInvalidRequestError()

        request = MSGPACKRPCRequest()
        request.one_way = True
        request.method = req[1]

        params = req[2]
        # params should not be None according to the spec; if there are
        # no params, an empty array must be used
        if isinstance(params, list):
            request.args = params
        else:
            raise MSGPACKRPCInvalidParamsError(request_id=req[1])

        return request

    def _parse_request(self, req):
        if not isinstance(req[2], six.string_types):
            raise MSGPACKRPCInvalidRequestError(request_id=req[1])

        request = MSGPACKRPCRequest()
        request.one_way = False
        request.method = req[2]
        request.unique_id = req[1]

        params = req[3]
        # params should not be None according to the spec; if there are
        # no params, an empty array must be used
        if isinstance(params, list):
            request.args = params
        else:
            raise MSGPACKRPCInvalidParamsError(request_id=req[1])

        return request

    def raise_error(
        self, error: Union["MSGPACKRPCErrorResponse", Dict[str, Any]]
    ) -> "MSGPACKRPCError":
        """Recreates the exception.

        Creates a :py:class:`~tinyrpc.protocols.msgpackrpc.MSGPACKRPCError`
        instance and raises it.

        This allows the error code and the message of the original exception to
        propagate into the client code.

        The :py:attr:`~tinyrpc.protocols.MSGPACKProtocol.raises_error` flag
        controls if the exception object is raised or returned.

        :returns: the exception object if it is not allowed to raise it.
        :raises MSGPACKRPCError: when the exception can be raised.
            The exception object will contain ``message`` and ``code``.
        """
        exc = MSGPACKRPCError(error)
        if self.raises_errors:
            raise exc
        return exc