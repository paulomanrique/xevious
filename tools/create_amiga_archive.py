import subprocess,os,glob,shutil,pathlib

progdir = pathlib.Path(os.path.join(os.path.dirname(__file__),os.pardir)).absolute()

gamename = "xevious"
# JOTD path for cranker, adapt to wh :)
os.environ["PATH"] += os.pathsep+r"K:\progs\cli"

cmd_prefix = ["make","-f",progdir/"makefile.am"]

subprocess.check_call(cmd_prefix+["clean"],cwd=os.path.join(progdir,"src"))

for s in ["convert_sounds.py","convert_graphics.py"]:
    subprocess.check_call(["cmd","/c",s],cwd=os.path.join(progdir,"assets","amiga"))

subprocess.check_call(cmd_prefix+["RELEASE_BUILD=1"],cwd=os.path.join(progdir,"src"))
# create archive

outdir = progdir / "dist" / f"{gamename}_HD"
if os.path.exists(outdir):
    shutil.rmtree(outdir)

outdir.mkdir(exist_ok=True,parents=True)

for file in ["readme.md","instructions.txt",gamename,f"{gamename}.slave"]:
    shutil.copy(os.path.join(progdir,file),outdir)

shutil.copy(os.path.join(progdir,"assets","amiga","Xevious.info"),outdir)


# pack the file for floppy
subprocess.check_output(["cranker_windows.exe","-f",os.path.join(progdir,gamename),"-o",os.path.join(progdir,f"{gamename}.rnc")])


arcname = progdir / f"Xevious1200_HD.lha"
arcname.unlink(missing_ok=True)
cmd = ["lha","-r","a",arcname,"*"]

subprocess.run(cmd,cwd=outdir.parent,check=True)