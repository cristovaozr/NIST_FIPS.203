#!/usr/bin/env python3
#
# alice.py - Keygen and decaps user of the ML-KEM key exchange procedure
#
# Author: Cristóvão Zuppardo Rufino <cristovao.rufino@ufpe.br>, <cristovaozr@gmail.com>
#
# License: Please see LICENSE file for the licensing of this work
#

import sys
import logging
import argparse
import json
import socket

from mlkem.implementation.mlkem import MLKEM
from mlkem.auxiliary.constants import FIPS203MLKEM512

logging.basicConfig(level=logging.DEBUG)


def get_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p", "--params",
        metavar="param_file",
        help="Parameter file",
        default="alice_params.json"
    )
    parser.add_argument(
        "-a", "--address",
        metavar="bob_address_full",
        help="Bob's address in IP:PORT format",
        default=None
    )

    return parser


def send_ek_to_bob(address: str, port: int, ek: bytes) -> bool:
    try:
        with socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM) as bob_socket:
            bob_address = (address, port)
            bob_socket.connect(bob_address)
            bob_socket.sendall(ek)
        return True

    except ConnectionRefusedError as e:
        return False


def wait_for_bob_response(port: int) -> bytes:
    CIPHER_TEXT_SIZE_IN_BYTES = 768
    with socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM) as alice_socket:
        alice_socket.bind(("localhost", port))
        alice_socket.listen()
        alice_conn, alice_addr = alice_socket.accept()
        with alice_conn:
            cipher_text = bytearray()
            while len(cipher_text) < CIPHER_TEXT_SIZE_IN_BYTES:
                data = alice_conn.recv(CIPHER_TEXT_SIZE_IN_BYTES - len(cipher_text))
                if not data:
                    break
                cipher_text += data

            return cipher_text


def main() -> int:
    logger = logging.getLogger("main")
    logger.debug("Parsing parameters")
    parser = get_argparse()
    args = parser.parse_args(sys.argv[1:])
    print(args)
    param_file = args.params

    logger.debug("Starting alice app, with FIPS203MLKEM512 configuration")
    logger.debug(f"Loading 'd' and 'z' values from {param_file}")
    try:
        with open(param_file, "r") as fp:
            params = json.load(fp)

    except FileNotFoundError as e:
        logger.error(f"Could not find parameter file {param_file}! Aborting!")
        return 1

    alice_mlkem = MLKEM(FIPS203MLKEM512())
    # FIXME: Inputs "d" and "z" should be generated by an approved RBG as recommended
    # in SP 800-90A, SO 800-90B and SP 800-90C. For now these values are fixed in order
    # to allow debugging
    d = params.get("d", None)
    z = params.get("z", None)

    if d is None or z is None:
        logger.error(f"Missing parameters in {param_file}! Please fix this!")
        return 1

    d = bytearray.fromhex(d)
    z = bytearray.fromhex(z)

    logger.warning("Generating key pair using 'fixed' data")
    ek, dk = alice_mlkem.KeyGen(d, z)

    bob_address_full = args.address
    if bob_address_full is None:
        logger.error("No address provided for Bob! He will be sad :'(")
        return 1

    bob_address = bob_address_full.split(":")[0]
    bob_port = int(bob_address_full.split(":")[1])
    logger.debug(f"Sending Bob the ek at {bob_address}:{bob_port}")
    logger.debug(f"The amount if data we are sending is {len(ek)} bytes")
    if not send_ek_to_bob(bob_address, bob_port, ek):
        logger.error(f"Failed sending ek to {bob_address}:{bob_port}!")
        return 1

    connections = params.get("connections", None)
    listen_port = 0
    if connections:
        listen_port = connections.get("port", 0)
    else:
        logger.error(f"No 'connection' section in {param_file}! Please fix this!")
        return 1
    if listen_port < 1024:
        logger.error(f"Port provided is {listen_port}, which cannot be easily used. Please choose another port!")
        return 1

    logger.debug("Waiting for Bob's response...")
    ciphered_text = wait_for_bob_response(listen_port)

    logger.debug("Got Bob's response! Retrieving the shared message...")
    alice_k = alice_mlkem.Decaps(dk, ciphered_text)

    logger.debug("Shared secret obtained!")
    logger.debug(f"It should be {alice_k.hex()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
