"""Read the compact webMAN MOD temperature response."""
from html import unescape
from ipaddress import IPv4Address, IPv4Network
import re

LAN_NETWORKS = tuple(IPv4Network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
TEMPERATURES = re.compile(r'\bCPU:\s*(\d{1,3})\s*°\s*C\s*\|\s*RSX:\s*(\d{1,3})\s*°\s*C\b')
MAX_RESPONSE = 16 * 1024


def temperature_url(host):
    address = IPv4Address(host)
    if not any(address in network for network in LAN_NETWORKS):
        raise ValueError('Enter your PS3’s private LAN IPv4 address.')
    return f'http://{address}/cpursx_ps3'


def parse_temperatures(data):
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    match = TEMPERATURES.search(unescape(text))
    if match:
        cell, rsx = map(int, match.groups())
        if all(0 < value <= 125 for value in (cell, rsx)):
            return cell, rsx
    raise ValueError('The response did not contain valid webMAN MOD temperatures.')
