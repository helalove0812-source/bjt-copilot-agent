def main(argv=None):
    del argv
    from start_web import main as start_web_main

    return start_web_main()


if __name__ == '__main__':
    raise SystemExit(main())
