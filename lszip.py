import requests
import sys
import struct

debug = True

if debug:
    import httplib
    httplib.HTTPConnection.debuglevel = 5

# Structure "End of central directory(ECD)" supports variable length
# comments at the end of file. Length of comment is specified by 2 bytes
# unsigned integer field in ECD. 
ZIP_ECD_MAX_COMMENT = (1 << 8*2) - 1

# Structure of "End of central directory" specified by standard
# excluding comment as its length is not known beforehand
structECD = '<I4HIIH'
sizeECD = struct.calcsize(structECD)

# First 4 bytes of ECD should match this
signECD = 0x06054b50

# Indices of entries in ECD
_ECD_SIGNATURE = 0
_ECD_DISK_NUMBER = 1
_ECD_DISK_START = 2
_ECD_ENTRIES_THIS_DISK = 3
_ECD_ENTRIES_TOTAL = 4
_ECD_SIZE = 5
_ECD_OFFSET = 6
_ECD_COMMENT_SIZE = 7


# Structure of "Central Directory(CD) Header"
# excluding variable fields: file_name, extra_field, and file_comment
structCD = '<I6H3I5H2I'
sizeCD = struct.calcsize(structCD)

# First 4 bytes of CD header should match this
signCD = 0x02014b50

# Indices of entries in CD
# indexes of entries in the central directory structure
_CD_SIGNATURE = 0
_CD_VERSION_MADE_BY = 1
_CD_VERSION_TO_EXTRACT = 2
_CD_COMPRESSION = 3
_CD_GP_BIT_FLAG = 4
_CD_TIME = 5
_CD_DATE = 6
_CD_CRC = 7
_CD_COMPRESSED_SIZE = 8
_CD_UNCOMPRESSED_SIZE = 9
_CD_FILENAME_LENGTH = 10
_CD_EXTRA_FIELD_LENGTH = 11
_CD_COMMENT_LENGTH = 12
_CD_DISK_NUMBER_START = 13
_CD_INTERNAL_FILE_ATTRIBUTES = 14
_CD_EXTERNAL_FILE_ATTRIBUTES = 15
_CD_LOCAL_HEADER_OFFSET = 16


def generate_range_header(lowByte=0, highByte=''):
    '''
    Returns dict such as {'Range': 'bytes=22-300'}
    as per HTTP/1.1 description
    http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.35
    Note that both end-values are inclusive.
    '''
    if lowByte < 0:
        # Low byte is negative. Means backward indexing
        # High byte not significant
        # Eg: {'Range': 'bytes=-22'} returns last 22 bytes
        return {'Range': 'bytes=' + str(lowByte)}

    # Eg: {'Range': 'bytes=22-200'} , {'Range': 'bytes=22-'}  
    range = 'bytes=%s-%s' %(lowByte, highByte)
    return {'Range': range}

def zip_is_valid_ecd(bytes):
    '''
    Given bytes of data, this function validates it for "End of Central Directory"
    entry. 
    
    It checks for two scenarios: 
    * ECD with no ZIP archive comment
    * ECD with ZIP archive comment
    '''
    
    # Unpack it, check signature and check comment's length
    ecd = struct.unpack(structECD, bytes[: sizeECD])
    
    if ecd[_ECD_SIGNATURE] != int(signECD):
        return False

    # Signature is correct. Check comment length's validity
    if (sizeECD + ecd[_ECD_COMMENT_SIZE]) != len(bytes):
        return False
    
    return True


def zip_get_ecd_index(bytes):
    '''
    Given bytes of data, this function searches for "End of Central Directory" Entry and
    returns its index.
    '''
    if len(bytes) < sizeECD:
        return None
    # Start at minimum index from end, where ECD can exist
    startIndex = len(bytes) - sizeECD
    
    while startIndex >= 0:
        if zip_is_valid_ecd(bytes[startIndex:]):
            # Found
            return startIndex
        startIndex -= 1
    return None


def main():
    url = sys.argv[1]

    s = requests.Session()
    headers = generate_range_header(lowByte=-sizeECD)

    r = s.get(url, headers=headers)

    print r.content
    sys.stdout.flush()
    assert r.status_code == 206

    end_of_central_dir = struct.unpack(structECD, r.content)
    start_offset = end_of_central_dir[6]
    assert end_of_central_dir[_ECD_SIGNATURE] == int(signECD)

    print "Now requesting bytes from:" + str(start_offset)
    headers = generate_range_header(start_offset)

    r = s.get(url, headers=headers)


    i = 0
    file_count = 0
    while i + sizeCD < len(r.content) - sizeECD:
        central_dir_header = struct.unpack(structCD, r.content[i:i+sizeCD])
        
        if central_dir_header[0] != int(signCD):
            break
        
        filename_length = central_dir_header[_CD_FILENAME_LENGTH]
        extra_field_length = central_dir_header[_CD_EXTRA_FIELD_LENGTH]
        file_comment_length = central_dir_header[_CD_COMMENT_LENGTH]

        filename = struct.unpack('<' + str(filename_length) + 's',
                                 r.content[i + sizeCD:(i + sizeCD + filename_length)])
        print filename[0]
        i = i+ sizeCD + filename_length + extra_field_length + file_comment_length

        file_count += 1

    assert end_of_central_dir[_ECD_ENTRIES_TOTAL] == file_count

    
if __name__ == '__main__':
    main()



    
