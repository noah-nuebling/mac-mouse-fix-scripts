
# Calling C / Objc functions
#   Should probably just use PyObjc

#
# Micro lib for calling objc methods
#

from ctypes import *
import ctypes.util as cutil


def mflib(libname):
    if not hasattr(mflib, 'cache'): mflib.cache = {}
    result = mflib.cache.get(libname, None)
    if not result:
        result = cdll.LoadLibrary(cutil.find_library(libname))
        mflib.cache[libname] = result
    return result

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
    if cstring is None: return None
    return cstring.decode('utf-8')

#
# Utils using the objc micro lib
#

def NSString_localizedStandardCompare(string1: str, string2: str) -> int:
    return mfsend(mfstr(string1), 'localizedStandardCompare:', mfstr(string2), types=(c_long, [c_void_p]))

def NSDictionary_stringForKey(dict: c_void_p|None, key: str) -> str|None:
    return mfdesc(mfsend(dict, "objectForKey:", mfstr(key), types=(c_void_p, [c_void_p])))

def isclass(obj: c_void_p|None, classname: str) -> bool:
    return mfsend(obj, "isKindOfClass:", mfcls(classname), types=(c_bool, [c_void_p]))

def NSPropertyListSerialization_loads(plist_string: str|None) -> c_void_p|None:
    """
    The benefit over plistlib is that this can load old-style plists. [Jan 2026]
    Returns pointer to NSDictionary or other plist type [Jan 2026]
    """

    NSUTF8StringEncoding = 4
    NSPropertyListImmutable = 0

    plist = mfsend(
        mfcls('NSPropertyListSerialization'),
        'propertyListWithData:options:format:error:',
        mfsend(mfstr(plist_string), 'dataUsingEncoding:', NSUTF8StringEncoding, types=(c_void_p, [c_ulong])),
        NSPropertyListImmutable,
        None,
        None,
        types=(c_void_p, [c_void_p, c_ulong, c_void_p, c_void_p])
    )
    
    return plist