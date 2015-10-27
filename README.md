# lszip
List ZIP archive's files without downloading the whole archive.
Useful for large ZIP archives ( < 4GB for now, doesn't support ZIP64)

## Requirements
* Python 2
* Web Server should support HTTP Range Request 

## Usage
### List all files in the archive
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
Download 1 - bios/hello.txt: Extracted to hello.txt
Download 4 - tmp/bright.tmp: Extracted to bright.tmp
```` 
### Download newfile.txt
````
# python lszip.py --nolist --download 5 http://example.com/zipfile.zip
Download 5 - newfile.txt: Extracted to newfile.txt
```` 
## Todo/Future Enhancements
* Support ZIP64
* Support Folder Download
* More testing
* Use temporary files rather than in-memory downloads
* ~~Selective Download~~

## References
[ZIP Archive Specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT)


