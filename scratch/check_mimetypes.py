import mimetypes
print(f".mp4: {mimetypes.guess_type('test.mp4')[0]}")
print(f".webm: {mimetypes.guess_type('test.webm')[0]}")
print(f".ogv: {mimetypes.guess_type('test.ogv')[0]}")
