import requests
import sys
import struct
import os
import zlib
import argparse

debug = False

if debug:
    import http.client
    http.client.HTTPConnection.debuglevel = 5

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


class CDEntry(object):
    ''' 
    Class for holding Central Directory Entry contents
    as well as file data and helper functions for extracting it
    '''
    # ID is assigned by classmethod "get_cd_entries"
    # Used for specifiying download in download mode
    id = None

    file_data = None

    is_dir = False

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

        if self.compressed_size == 0:
            self.is_dir = True

        self.compression_method = central_dir_header[_CD_COMPRESSION]

        self.filename = bytes[sizeCD:sizeCD + self.filename_length].decode('utf-8')
    def __str__(self):
        return '%s : %s' %(self.id, self.filename)

    @property    
    def total_size(self):
        ''' 
        Returns total size of Central Dir Entry equivalent to:
        cd_header + filename_length + comment_length + extra_field_length
        '''
        return sizeCD + self.filename_length + self.extra_field_length + self.comment_length

    


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

        # Check if we are not getting partial content
        if not int(response.headers['content-length']) < ZIP_ECD_MAX_SIZE:
            assert response.status_code == 206
        return response


    def get_ecd(self):
        '''
        Returns ECD array by downloading ZIP_ECD_MAX_SIZE bytes
        '''
        # Get around 65kb of data in case the file has archive comment
        request_data_size = ZIP_ECD_MAX_SIZE
        response = self.get_response(lowByte=-(request_data_size))
        
        
        self.ecd = zip_get_ecd(response.content)
        self.ecd_request_data = response.content
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

        r = self.get_response(lowByte=cd_start_offset)
        return r.content


    def get_cd_entries(self):
        '''
        Returns a list of CDEntry objects, also save it inside the object
        '''
        # Get bytes from which Central Directory entries start
        bytes = self.get_cd_bytes()

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

        self.cd_entries = cd_entries

        return cd_entries

    def get_local_header(self, cd_entry):
        '''
        Returns local header for given central dir entry
        '''
        local_header_offset = cd_entry.local_header_offset
        r = self.get_response(local_header_offset, local_header_offset + sizeLHeader - 1)

        local_header = struct.unpack(structLHeader, r.content)
        return local_header

    def get_file_data(self, cd_entry, local_header):
        '''
        Returns file data represented by given local_header and cd_entry
        '''
        data_start_offset = cd_entry.local_header_offset \
                                    + sizeLHeader   \
                                    + local_header[_LH_FILENAME_LENGTH] \
                                    + local_header[_LH_EXTRA_FIELD_LENGTH]
        r = self.get_response(data_start_offset, data_start_offset + local_header[_LH_COMPRESSED_SIZE] - 1)
        return r.content

    def extract(self, cd_entry, filename=''):
        '''
        Extracts the data represented by cd_entry to given filename
        '''
        if not filename:
            filename = os.path.basename(cd_entry.filename)

        if cd_entry.is_dir:
            raise NotImplementedError('Directory Download is not implemented')

        if cd_entry.compression_method not in (_COMPR_DEFLATE, _COMPR_STORED):
            return -1
        with open(filename, 'wb') as outfile:
            if cd_entry.compression_method == _COMPR_DEFLATE:
                # Negative value suppresses standard gzip header check
                outfile.write(zlib.decompress(cd_entry.file_data, -15))
            elif cd_entry.compression_method == _COMPR_STORED:
                outfile.write(cd_entry.file_data)

            print("Download %s : Extracted to %s" %(cd_entry.filename, filename))



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="ZIP File's URL")
    parser.add_argument("--nolist", action="store_true", default=False, help="Disable Listing of Files")
    parser.add_argument("--download", type=str,
                       help='List of Comma Separated IDs to download. IDs are listed in listing mode.')
    args = parser.parse_args()

    url = args.url

    retriever = ZIPRetriever(url)
    retriever.get_cd_entries()

    assert retriever.ecd[_ECD_ENTRIES_TOTAL] == len(retriever.cd_entries)

    if not args.nolist:
        for cd_entry in retriever.cd_entries:
            print(cd_entry)
    
    if args.download:
        download_ids = args.download.split(',')
        for id, cd_entry in enumerate(retriever.cd_entries):
            if str(id) in download_ids:
                if cd_entry.is_dir:
                    print("Download %s - %s:Directory Download not supported" %(id, cd_entry.filename))
                    continue
                local_header = retriever.get_local_header(cd_entry)
                data = retriever.get_file_data(cd_entry, local_header)

                cd_entry.file_data = data
                # Some archivers set this value only in local header
                cd_entry.compression_method = local_header[_LH_COMPRESSION]
                retriever.extract(cd_entry)


    
if __name__ == '__main__':
    main()



    
