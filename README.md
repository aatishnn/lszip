# lszip
List ZIP archive's files without downloading the whole archive.
Useful for large ZIP archives ( < 4GB for now, doesn't support ZIP64)

## Requirements
* Python 3
* Web Server should support HTTP Range Request 

## Examples
### List all files and directories in the archive
````
# python lszip.py http://example.com/zipfile.zip
0 : bios/
1 : bios/hello.txt 
2 : bios/hello2.txt
3 : tmp/
4 : tmp/bright.tmp
5 : newfile.txt 
```` 
### Download hello.txt and bright.tmp
````
# python lszip.py --nolist --download 1,4 http://example.com/zipfile.zip
```` 
### Download newfile.txt
````
# python lszip.py --nolist --download 5 http://example.com/zipfile.zip
````
### Download directory `tmp` and all its contents
````
# python lszip.py --nolist --download 3 http://example.com/zipfile.zip
````

By default, this program will download files in current working directory but 
it will create folder trees if needed. This directory can be changed by 
using `--cwd`.

## Usage

````
usage: lszip.py [-h] [--nolist] [--download DOWNLOAD] [--cwd CWD] url

positional arguments:
  url                  ZIP File's URL

optional arguments:
  -h, --help           show this help message and exit
  --nolist             Disable Listing of Files
  --download DOWNLOAD  List of Comma Separated IDs to download. IDs are listed
                       in listing mode.
  --cwd CWD            Set current working directory where downloads are done.
                       Defaults to current directory.
````

*Expect bugs*
## Todo/Future Enhancements
* Support ZIP64
* ~~Support Folder Download~~
* More testing
* Use temporary files rather than in-memory downloads
* ~~Selective Download~~

## References
[ZIP Archive Specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT)


