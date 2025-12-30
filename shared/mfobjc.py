
# Calling C / Objc functions
#   Should probably just use PyObjc

#
# Micro lib for calling objc methods
#

from ctypes import *
import ctypes.util as cutil

def mflib(libname):
    return cdll.LoadLibrary(cutil.find_library(libname))

def mfcstr(s):
    return s.encode('utf-8')

def mffunc(lib, restype, fname, argtypes):
    f = lib[fname]
    f.restype = restype
    f.argtypes = argtypes
    return f

def mfcls(clsname): 
    return mffunc(mflib('objc'), c_void_p, 'objc_getClass', [c_char_p])(mfcstr(clsname))

def mfsend(obj, selname, *args, types=(c_void_p, [])): 
    sel     = mffunc(mflib('objc'), c_void_p, 'sel_registerName', [c_char_p])(mfcstr(selname))
    msgsend = mffunc(mflib('objc'), types[0], 'objc_msgSend', [c_void_p, c_void_p] + types[1])
    return msgsend(obj, sel, *args)

def mfstr(s): 
    return mfsend(mfcls('NSString'), 'stringWithUTF8String:', mfcstr(s), types=(c_void_p, [c_char_p]))  # Returns autoreleased      –> in a long-running Python script you may wanna use an NSAutoReleasePool [Dec 2025]

def mfdesc(obj):
    nsstring = mfsend(obj, 'description', types=(c_void_p, []))     # Returns autoreleased (I think)
    cstring  = mfsend(nsstring, 'UTF8String', types=(c_char_p, []))
    return cstring.decode('utf-8')

#
# Utils using the objc micro lib
#

def NSString_localizedStandardCompare(string1: str, string2: str) -> int:
    return mfsend(mfstr(string1), 'localizedStandardCompare:', mfstr(string2), types=(c_long, [c_void_p]))
