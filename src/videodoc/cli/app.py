import typer

from videodoc.cli.commands import (
    ask,
    chunk,
    code,
    doctor,
    embed,
    extract_audio,
    frames,
    generate,
    ingest,
    index,
    init,
    link,
    list_projects,
    ocr,
    outline,
    path as path_cmd,
    scan,
    setup,
    transcribe,
    unlink,
)

app = typer.Typer(name="videodoc", help="VideoDocRAG command-line interface.", no_args_is_help=True)
app.command("init")(init.init_command)
app.command("list")(list_projects.list_command)
app.command("link")(link.link_command)
app.command("unlink")(unlink.unlink_command)
app.command("path")(path_cmd.path_command)
app.command("scan")(scan.scan_command)
app.command("ingest")(ingest.ingest_command)
app.command("extract-audio")(extract_audio.extract_audio_command)
app.command("transcribe")(transcribe.transcribe_command)
app.command("frames")(frames.frames_command)
app.command("ocr")(ocr.ocr_command)
app.command("code")(code.code_command)
app.command("chunk")(chunk.chunk_command)
app.command("embed")(embed.embed_command)
app.command("index")(index.index_command)
app.command("ask")(ask.ask_command)
app.command("outline")(outline.outline_command)
app.command("generate")(generate.generate_command)
app.command("doctor")(doctor.doctor_command)
app.command("setup")(setup.setup_command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
