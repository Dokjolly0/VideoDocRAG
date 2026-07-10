import typer

from videodoc.cli.commands import ingest, init, link, list_projects, path as path_cmd, scan, unlink

app = typer.Typer(name="videodoc", help="VideoDocRAG command-line interface.", no_args_is_help=True)
app.command("init")(init.init_command)
app.command("list")(list_projects.list_command)
app.command("link")(link.link_command)
app.command("unlink")(unlink.unlink_command)
app.command("path")(path_cmd.path_command)
app.command("scan")(scan.scan_command)
app.command("ingest")(ingest.ingest_command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
