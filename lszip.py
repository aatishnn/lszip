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

# Structure of "Local File Header"
# excluding variable fields: file_name and extra_field
structLHeader = '<I5H3I2H'
sizeLHeader = struct.calcsize(structLHeader)

# First 4 bytes of Local File header should match this
signLHeader = 0x04034b50

# Indices of entries in Local File header
_CD_SIGNATURE = 0
_CD_VERSION_TO_EXTRACT = 1
_CD_GP_BIT_FLAG = 2
_CD_COMPRESSION = 3
_CD_TIME = 4
_CD_DATE = 5
_CD_CRC = 6
_CD_COMPRESSED_SIZE = 7
_CD_UNCOMPRESSED_SIZE = 8
_CD_FILENAME_LENGTH = 9
_CD_EXTRA_FIELD_LENGTH = 10


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

def zip_get_valid_ecd(bytes):
    '''
    Given bytes of data, this function validates it for 
    "End of Central Directory" entry and returns it, None otherwise
    
    It checks for two scenarios: 
    * ECD with no ZIP archive comment
    * ECD with ZIP archive comment
    
    Any extra bytes invalidates the data.
    '''
    
    # Unpack it, check signature and check comment's length
    ecd = struct.unpack(structECD, bytes[: sizeECD])
    
    # Check signature
    if ecd[_ECD_SIGNATURE] != int(signECD):
        return None

    # Signature is correct. Check comment length's validity
    if (sizeECD + ecd[_ECD_COMMENT_SIZE]) != len(bytes):
        return None
    
    return ecd


def zip_get_ecd(bytes):
    '''
    Given bytes of data, this function searches for 
    "End of Central Directory" Entry and returns it, None otherwise.
    '''
    if len(bytes) < sizeECD:
        return None
    # Start at minimum index from end, where ECD can exist
    startIndex = len(bytes) - sizeECD
    
    while startIndex >= 0:
        ecd = zip_get_valid_ecd(bytes[startIndex:])
        if ecd:
            # Found
            return ecd
        startIndex -= 1
    return None

def index_in_subarray(index, subarray_size, array_size):
    '''
    Checks whether the index of larger array lies inside the sub-array
    made from skipping certain elements from the "front".
    Eg: Array a = [2, 3, 44, 55, 666]
        Subarray b = [44, 55, 666]
        index_in_sub_array(1, len(b), len(a)) = False
        index_in_sub_array(2, len(b), len(a)) = True
    No check is done for out-of-bounds
    '''
    if index < array_size - subarray_size:
        return False
    return True


def main():
    url = sys.argv[1]

    s = requests.Session()
    # Get around 65kb of data in case the file has archive comment
    request_data_size = sizeECD + ZIP_ECD_MAX_COMMENT
    headers = generate_range_header(lowByte=-(request_data_size))

    r = s.get(url, headers=headers)
    print r.headers
    # print r.content
    sys.stdout.flush()
    assert r.status_code == 206
    
    # Get archive size from reply header 'Content-Range' as 22-23232/23233
    archive_size = int(r.headers['Content-Range'].split('-')[1].split('/')[1])
    ecd = zip_get_ecd(r.content)

    if not ecd:
        print "Not a valid ZIP file. Exiting.." 
        sys.exit(-1)

    # Get Central Directory start offset relative to whole ZIP archive
    cd_start_offset = ecd[_ECD_OFFSET]

    # i represents index where Central Directory starts in request_data(r.content)
    i = 0
    # Check if Central Directory starts outside bytes we have already downloaded
    if not index_in_subarray(cd_start_offset, request_data_size, archive_size):
        # Download Central Directory
        print "Requesting Central Directory Entry"
        print "Now requesting bytes from:" + str(cd_start_offset)
        headers = generate_range_header(cd_start_offset)
        r = s.get(url, headers=headers)

    else:
        # Modify index (in terms of request_data_size) to start at cd_start_offset
        # Eg: archive size = 12, request_data_size = 10, cd_start_offset=4
        # Then, i = 4 - (12-10)

        i = cd_start_offset - (archive_size - request_data_size)

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

    assert ecd[_ECD_ENTRIES_TOTAL] == file_count

    
if __name__ == '__main__':
    main()



    
