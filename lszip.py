import requests
import sys
import struct
import os
import zlib
import argparse

debug = False

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

ZIP_ECD_MAX_SIZE = sizeECD + ZIP_ECD_MAX_COMMENT

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
_LH_SIGNATURE = 0
_LH_VERSION_TO_EXTRACT = 1
_LH_GP_BIT_FLAG = 2
_LH_COMPRESSION = 3
_LH_TIME = 4
_LH_DATE = 5
_LH_CRC = 6
_LH_COMPRESSED_SIZE = 7
_LH_UNCOMPRESSED_SIZE = 8
_LH_FILENAME_LENGTH = 9
_LH_EXTRA_FIELD_LENGTH = 10


# Compression Methods
_COMPR_STORED = 0
_COMPR_DEFLATE = 8

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

def get_file(session, url, local_header_offset, filename):
    print "Requesting local file header"
    headers = generate_range_header(local_header_offset, local_header_offset + sizeLHeader - 1)
    r = session.get(url, headers=headers)
    local_header = struct.unpack(structLHeader, r.content)
    compression_method = local_header[_LH_COMPRESSION]
    print "Compr Size: %s  file len: %s  extra len: %s" %(local_header[_LH_COMPRESSED_SIZE], local_header[_LH_FILENAME_LENGTH], local_header[_LH_EXTRA_FIELD_LENGTH])

    if compression_method == _COMPR_STORED:
        file_data_start_offset = local_header_offset \
                                    + sizeLHeader   \
                                    + local_header[_LH_FILENAME_LENGTH] \
                                    + local_header[_LH_EXTRA_FIELD_LENGTH] 
        headers = generate_range_header(file_data_start_offset, file_data_start_offset + local_header[_LH_COMPRESSED_SIZE] - 1)
        print "Downloading data " + str(headers)
        r = session.get(url, headers=headers)
        with open(os.path.basename(filename), 'wb') as outfile:
            outfile.write(r.content)
            print "Wrote data to : " + os.path.basename(filename)

    elif compression_method == _COMPR_DEFLATE:
        print "Extracting deflated file..."
        file_data_start_offset = local_header_offset \
                                    + sizeLHeader   \
                                    + local_header[_LH_FILENAME_LENGTH] \
                                    + local_header[_LH_EXTRA_FIELD_LENGTH] 
        headers = generate_range_header(file_data_start_offset, file_data_start_offset + local_header[_LH_COMPRESSED_SIZE] - 1)
        print "Downloading data " + str(headers)
        r = session.get(url, headers=headers)
        with open(os.path.basename(filename), 'wb') as outfile:
            # Negative value suppresses standard gzip header check
            outfile.write(zlib.decompress(r.content, -15))
            print "Wrote data to : " + os.path.basename(filename)
    else:
        print "Unsupported Compression Method"


class CDEntry(object):
    ''' Central Directory Entry '''
    # ID is assigned by classmethod "get_cd_entries"
    # Used for specifiying download in download mode
    id = None

    def __init__(self, bytes):
        ''' 
        bytes: Raw bytes including filename, extra_field and file_comment. Extra bytes
               are neglected
        '''
        central_dir_header = struct.unpack(structCD, bytes[:sizeCD])
        
        if central_dir_header[_CD_SIGNATURE] != int(signCD):
            raise Exception('Bad Central Directory Header')

        self.filename_length = central_dir_header[_CD_FILENAME_LENGTH]
        self.extra_field_length = central_dir_header[_CD_EXTRA_FIELD_LENGTH]
        self.comment_length = central_dir_header[_CD_COMMENT_LENGTH]
        self.local_header_offset = central_dir_header[_CD_LOCAL_HEADER_OFFSET]
        self.compressed_size = central_dir_header[_CD_COMPRESSED_SIZE]

        self.filename = struct.unpack('<' + str(self.filename_length) + 's',
                                 bytes[sizeCD:sizeCD + self.filename_length])[0]
    def __str__(self):
        return '%s : %s' %(self.id, self.filename)
    @property    
    def total_size(self):
        ''' 
        Returns total size of Central Dir Entry equivalent to:
        cd_header + filename_length + comment_length + extra_field_length
        '''
        return sizeCD + self.filename_length + self.extra_field_length + self.comment_length

    @classmethod
    def get_cd_entries(cls, bytes):
        '''
        Returns a list of CDEntry objects from given bytes
        '''
        cd_entries = []
        i = 0
        entry_pointer = 0
        # len(bytes[entry_pointer:]) checked to ensure that we are not out of bytes
        while (sizeCD < len(bytes) - sizeECD) and (len(bytes[entry_pointer:]) >= sizeCD):
            cd_entry = CDEntry(bytes[entry_pointer:])
            cd_entry.id = i
            cd_entries.append(cd_entry)
            entry_pointer += cd_entry.total_size
            i += 1

        return cd_entries


class ZIPRetriever(object):
    '''
    Download Helper class that uses a single requests session
    '''
    session = None
    url = None

    # Populated by get_ecd_bytes
    archive_size = None

    ecd = None

    def __init__(self, url=''):
        self.session = requests.Session()
        self.url = url

    def get_response(self, lowByte=0, highByte=''):
        '''
        Low level function to get response of request from lowByte to highByte
        whose descriptions are as same as in generate_range_header
        '''
        headers = generate_range_header(lowByte=lowByte, highByte=highByte)
        response = self.session.get(self.url, headers=headers)
        assert response.status_code == 206
        return response


    def get_ecd(self):
        '''
        Returns ECD array by downloading ZIP_ECD_MAX_SIZE bytes
        '''
        # Get around 65kb of data in case the file has archive comment
        request_data_size = ZIP_ECD_MAX_SIZE
        response = self.get_response(lowByte=-(request_data_size))
        
        # Populate archive size from reply header like : 'Content-Range': 22-23232/23233
        self.archive_size = int(response.headers['Content-Range'].split('-')[1].split('/')[1])
        
        self.ecd = zip_get_ecd(response.content)

        return self.ecd

    def get_cd_bytes(self):
        '''
        Returns bytes from which central directory starts
        '''
        ecd = self.get_ecd()

        if not ecd:
            raise Exception('Bad Zip File')

        # Get Central Directory start offset relative to whole ZIP archive
        cd_start_offset = ecd[_ECD_OFFSET]

        # i represents index where Central Directory starts in request_data(r.content)
        i = 0
        # Check if Central Directory starts outside bytes we have already downloaded
        if not index_in_subarray(cd_start_offset, ZIP_ECD_MAX_SIZE, self.archive_size):
            # Download Central Directory
            print "Requesting Central Directory Entry"
            print "Now requesting bytes from:" + str(cd_start_offset)
            r = self.get_response(lowByte=cd_start_offset)

        else:
            # Modify index (in terms of request_data_size == ZIP_ECD_MAX_SIZE ) to 
            # start at cd_start_offset
            # Eg: archive size = 12, request_data_size = 10, cd_start_offset=4
            # Then, i = 4 - (12-10)

            i = cd_start_offset - (self.archive_size - ZIP_ECD_MAX_SIZE)

        return r.content[i:]



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="ZIP File's URL")
    args = parser.parse_args()

    url = args.url

    retriever = ZIPRetriever(url)    
    print type(retriever)

    central_dir_data = retriever.get_cd_bytes()

    cd_entries = CDEntry.get_cd_entries(central_dir_data)
    for cd_entry in cd_entries:
        print cd_entry

        # download_file = raw_input('Download ? [Y/N] : ')
        # if download_file.lower() == 'y':
        #     get_file(s, url, local_header_offset, filename[0])

    assert retriever.ecd[_ECD_ENTRIES_TOTAL] == len(cd_entries)

    
if __name__ == '__main__':
    main()



    
