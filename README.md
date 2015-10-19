# lszip
List ZIP archive's files without downloading the whole archive
Useful for large ZIP archives ( < 4GB for now, doesn't support ZIP64)

## Requirements
* Python 2
* Web Server should support HTTP Range Request 

## Usage
````
# lszip http://example.com/zipfile.zip
````  
## Todo/Future Enhancements
* Support ZIP64
* Selective Download


