def buildarg_from_dict(args):
    if args is None:
        return ""

    return " ".join(["--build-arg {}={}".format(k, v) for k, v in args.items()])
