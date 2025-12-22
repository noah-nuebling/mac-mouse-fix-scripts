
# Calling C / Objc functions
#   Should probably just use PyObjc

#
# Micro lib for calling objc methods
#

from ctypes import *
import ctypes.util as cutil

def mfobjc_lib(libname):
    return cdll.LoadLibrary(cutil.find_library(libname))

def mfobjc_cstr(s):
    return s.encode('utf-8')

def mfobjc_func(lib, restype, fname, argtypes):
    f = lib[fname]
    f.restype = restype
    f.argtypes = argtypes
    return f

def mfobjc_cls(clsname): 
    return mfobjc_func(mfobjc_lib('objc'), c_void_p, 'objc_getClass', [c_char_p])(mfobjc_cstr(clsname))

def mfobjc_send(obj, selname, *args, types=(c_void_p, [])): 
    sel     = mfobjc_func(mfobjc_lib('objc'), c_void_p, 'sel_registerName', [c_char_p])(mfobjc_cstr(selname))
    msgsend = mfobjc_func(mfobjc_lib('objc'), types[0], 'objc_msgSend', [c_void_p, c_void_p] + types[1])
    return msgsend(obj, sel, *args)

def mfobjc_str(s): 
    return mfobjc_send(mfobjc_cls('NSString'), 'stringWithUTF8String:', mfobjc_cstr(s), types=(c_void_p, [c_char_p]))  # Returns autoreleased      –> in a long-running Python script you may wanna use an NSAutoReleasePool [Dec 2025]

def mfobjc_desc(obj):
    nsstring = mfobjc_send(obj, 'description', types=(c_void_p, []))     # Returns autoreleased (I think)
    cstring  = mfobjc_send(nsstring, 'UTF8String', types=(c_char_p, []))
    return cstring.decode('utf-8')

#
# Utils using the micro lib
#

def NSString_localizedStandardCompare(string1: str, string2: str) -> int: # 
    return mfobjc_send(mfobjc_str(string1), 'localizedStandardCompare:', mfobjc_str(string2), types=(c_long, [c_void_p]))