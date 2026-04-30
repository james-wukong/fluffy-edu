import preprocessing.chunker as chunker


def main():
    print("Hello from app!")
    ck = chunker.SmartChunker(chunk_size=15, overlap=3)


if __name__ == "__main__":
    main()
