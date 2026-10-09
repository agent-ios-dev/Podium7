"""Opt-in synthetic AMD NOR provider for original AppleARMCHRPNVRAM.

This is alternative research hardware, not the physical n112ap NVMe storage.
"""
import struct
from analyze_firmware import device_tree
from nvram_handoff import empty_bank

BASE = 0x2f0000000
SIZE = 0x8000


def flash_image():
    return empty_bank() * 2 + bytes([255]) * (SIZE - 16384)


def attach(data):
    device_tree(data)
    seen = set()
    def encode(properties, children):
        out = struct.pack('<II', len(properties), len(children))
        for key, value in properties:
            out += key.ljust(32, b'\0') + struct.pack('<I', len(value)) + value + bytes((-len(value)) & 3)
        return out + b''.join(children)
    def walk(cursor, parent):
        count, children = struct.unpack_from('<II', data, cursor); cursor += 8
        properties = []
        for _ in range(count):
            key = data[cursor:cursor+32].split(b'\0')[0]
            size = struct.unpack_from('<I',data,cursor+32)[0] & 0x7fffffff
            cursor += 36
            properties.append((key,data[cursor:cursor+size])); cursor += (size+3)&~3
        names = dict(properties)
        path = parent + '/' + names.get(b'name',b'?').split(b'\0')[0].decode('ascii')
        encoded_children = []
        for _ in range(children):
            child,cursor = walk(cursor,path);encoded_children.append(child)
        if path == '/device-tree/chosen':
            for key,value in [(b'nvram-bank-count',2),(b'nvram-current-bank',0)]:
                if key in names and names[key] != bytes(4):
                    raise ValueError('CFI experiment requires untouched zero bank metadata')
                properties = [(k,v) for k,v in properties if k != key]
                properties.append((key,struct.pack('<I',value)))
            seen.add('chosen')
        if path == '/device-tree/arm-io':
            if b'podium7-nvram-cfi' in data:
                raise ValueError('CFI controller already exists')
            ranges = names.get(b'ranges',b'')
            if not any(child <= BASE - 0x200000000 < child+length and
                       parent_addr+BASE-0x200000000-child == BASE
                       for child,parent_addr,length in struct.iter_unpack('<QQQ',ranges)):
                raise ValueError('CFI address not covered by original arm-io range')
            region = encode([(b'name',b'nvram\0'),(b'compatible',b'nvram,chrp\0'),
                             (b'reg',struct.pack('<II',0,16384))],[])
            controller = encode([(b'name',b'podium7-nvram-cfi\0'),
                                 (b'compatible',b'nor-flash,cfi\0'),
                                 (b'device_type',b'nor-flash\0'),
                                 (b'#device-bytes',struct.pack('<I',1)),
                                 (b'#port-devices',struct.pack('<I',1)),
                                 (b'reg',struct.pack('<QQ',BASE-0x200000000,SIZE))],[region])
            encoded_children.append(controller);seen.add('arm-io')
        return encode(properties,encoded_children),cursor
    tree,end = walk(0,'')
    if end != len(data) or seen != {'chosen','arm-io'}:
        raise ValueError('missing CFI handoff nodes')
    device_tree(tree)
    return tree
