"""Generate ssis/FlightDWLoad/LoadFlightDW.dtsx: the SSIS control flow of the FlightDW load.

Seven Execute Process Tasks in a chain (green success arrows), each calling the same command the
README uses (docs/ssis-guide.md explains why sqlcmd and not Execute SQL Tasks):
  1 copy the CSVs to DataDir, 2 01_create_db, 3 02_stg_tables, 4 03_dw_tables, 5 04_load,
  6 99_checks, 7 05_grant_ssas_read.
Package variables RepoDir, DataDir and SqlInstance feed property expressions on every task, so the
package runs from any clone without editing paths.

Usage (repo root):  python tools/build_ssis_package.py      -> writes the .dtsx
Run it:             dtexec /File ssis\\FlightDWLoad\\LoadFlightDW.dtsx
The .dtsx is generated; never edit it by hand (re-run this script instead).
"""
import uuid
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "ssis" / "FlightDWLoad" / "LoadFlightDW.dtsx"

PACKAGE = "LoadFlightDW"
NS = uuid.UUID("5b1f0c6e-0d0e-4c0e-9a55-2f0a7d3c1f10")   # fixed namespace: GUIDs are reproducible

VARIABLES = [  # (name, default value)
    ("RepoDir", "."),   # relative: run dtexec from the repository root (no personal path in the package)
    ("DataDir", r"C:\fdw_data"),
    ("SqlInstance", r"localhost\SQLEXPRESS"),
]


def guid(name: str) -> str:
    return "{" + str(uuid.uuid5(NS, name)).upper() + "}"


def sqlcmd_args(script: str, extra: str = "") -> tuple:
    """(SSIS expression, resolved design value) for a sqlcmd call of sql/<script>."""
    repo, inst, data = VARIABLES[0][1], VARIABLES[2][1], VARIABLES[1][1]
    pre = "-S " + inst + " -E -b -f 65001 "
    value = pre + (f'-v DataDir="{data}" ' if extra else "") + f'-i "{repo}\\sql\\{script}"'
    expr = ('"-S " + @[User::SqlInstance] + " -E -b -f 65001 " + '
            + ('"-v DataDir=\\"" + @[User::DataDir] + "\\" " + ' if extra else "")
            + f'"-i \\"" + @[User::RepoDir] + "\\\\sql\\\\{script}\\""')
    return expr, value


def copy_args() -> tuple:
    repo, data = VARIABLES[0][1], VARIABLES[1][1]
    value = f'/c if not exist {data} mkdir {data} & copy /Y "{repo}\\data\\processed\\*.csv" {data}\\'
    expr = ('"/c if not exist " + @[User::DataDir] + " mkdir " + @[User::DataDir] + '
            '" & copy /Y \\"" + @[User::RepoDir] + "\\\\data\\\\processed\\\\*.csv\\" " + @[User::DataDir] + "\\\\"')
    return expr, value


def tasks() -> list:
    """(task name, executable, arguments expression, arguments value)."""
    cmd = r"C:\Windows\System32\cmd.exe"
    out = [("Copy CSVs to DataDir", cmd, *copy_args())]
    for name, script, extra in [("01 create database", "01_create_db.sql", ""),
                                ("02 staging tables", "02_stg_tables.sql", ""),
                                ("03 star schema", "03_dw_tables.sql", ""),
                                ("04 load", "04_load.sql", "datadir"),
                                ("99 checks", "99_checks.sql", ""),
                                ("05 grant cube read", "05_grant_ssas_read.sql", "")]:
        out.append((name, "sqlcmd.exe", *sqlcmd_args(script, extra)))
    return out


def executable_xml(i: int, name: str, exe: str, expr: str, value: str) -> str:
    ref = f"Package\\{name}"
    return f"""    <DTS:Executable
      DTS:refId={quoteattr(ref)}
      DTS:CreationName="Microsoft.ExecuteProcess"
      DTS:Description="Execute Process Task"
      DTS:DTSID="{guid('task' + name)}"
      DTS:ExecutableType="Microsoft.ExecuteProcess"
      DTS:LocaleID="-1"
      DTS:ObjectName={quoteattr(name)}
      DTS:TaskContact="Execute Process Task;Microsoft Corporation; Microsoft SQL Server v9; (C) 2004 Microsoft Corporation; All Rights Reserved;http://www.microsoft.com/sql/support/default.asp;1"
      DTS:ThreadHint="0">
      <DTS:Variables />
      <DTS:PropertyExpression
        DTS:Name="Arguments">{escape(expr)}</DTS:PropertyExpression>
      <DTS:ObjectData>
        <ExecuteProcessData
          Executable={quoteattr(exe)}
          Arguments={quoteattr(value)}
          RequireFullFileName="{'True' if exe.lower().endswith('cmd.exe') else 'False'}"
          FailTaskIfReturnCodeIsNotSuccessValue="True"
          SuccessValue="0"
          WindowStyle="Hidden" />
      </DTS:ObjectData>
    </DTS:Executable>"""


def layout_xml(names: list) -> str:
    """Design-time layout: one column of tasks, arrows between them."""
    w, h, gap, x0, y0 = 220, 42, 38, 40, 20
    nodes, edges = [], []
    for i, n in enumerate(names):
        nodes.append(f'<NodeLayout Size="{w},{h}" Id="Package\\{n}" TopLeft="{x0},{y0 + i * (h + gap)}" />')
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        top = y0 + i * (h + gap) + h
        cx = x0 + w / 2
        edges.append(
            f'<EdgeLayout Id="Package.PrecedenceConstraints[{a} to {b}]" TopLeft="{cx},{top}">'
            f'<EdgeLayout.Curve><mssgle:Curve StartConnector="{{assembly:Null}}" EndConnector="0,{gap}" '
            f'Start="0,0" End="0,{gap - 8}"><mssgle:Curve.Segments><mssgle:SegmentCollection Capacity="5">'
            f'<mssgle:LineSegment End="0,{gap - 8}" /></mssgle:SegmentCollection></mssgle:Curve.Segments>'
            f'</mssgle:Curve></EdgeLayout.Curve><EdgeLayout.Labels><EdgeLabelCollection /></EdgeLayout.Labels>'
            f'</EdgeLayout>')
    return ('<?xml version="1.0"?><Objects Version="8"><Package design-time-name="Package"><LayoutInfo>'
            '<GraphLayout Capacity="32" '
            'xmlns="clr-namespace:Microsoft.SqlServer.IntegrationServices.Designer.Model.Serialization;'
            'assembly=Microsoft.SqlServer.IntegrationServices.Graph" '
            'xmlns:mssgle="clr-namespace:Microsoft.SqlServer.Graph.LayoutEngine;assembly=Microsoft.SqlServer.Graph" '
            'xmlns:assembly="http://schemas.microsoft.com/winfx/2006/xaml">'
            + "".join(nodes) + "".join(edges) +
            '</GraphLayout></LayoutInfo></Package></Objects>')


def constraint_xml(a: str, b: str) -> str:
    ref = f"Package.PrecedenceConstraints[{a} to {b}]"
    frm, to = "Package\\" + a, "Package\\" + b
    return f"""    <DTS:PrecedenceConstraint
      DTS:refId={quoteattr(ref)}
      DTS:CreationName=""
      DTS:DTSID="{guid('pc' + a + b)}"
      DTS:From={quoteattr(frm)}
      DTS:LogicalAnd="True"
      DTS:ObjectName={quoteattr(f'{a} to {b}')}
      DTS:To={quoteattr(to)} />"""


def build() -> str:
    ts = tasks()
    names = [t[0] for t in ts]
    var_xml = "\n".join(
        f"""    <DTS:Variable
      DTS:CreationName=""
      DTS:DTSID="{guid('var' + n)}"
      DTS:IncludeInDebugDump="6789"
      DTS:Namespace="User"
      DTS:ObjectName="{n}">
      <DTS:VariableValue
        DTS:DataType="8">{escape(v)}</DTS:VariableValue>
    </DTS:Variable>""" for n, v in VARIABLES)
    exec_xml = "\n".join(executable_xml(i, *t) for i, t in enumerate(ts))
    pc_xml = "\n".join(constraint_xml(a, b) for a, b in zip(names, names[1:]))
    return f"""<?xml version="1.0"?>
<!-- LoadFlightDW.dtsx: GENERATED by tools/build_ssis_package.py. Do not edit by hand. -->
<DTS:Executable xmlns:DTS="www.microsoft.com/SqlServer/Dts"
  DTS:refId="Package"
  DTS:CreationName="Microsoft.Package"
  DTS:DTSID="{guid('package')}"
  DTS:ExecutableType="Microsoft.Package"
  DTS:LastModifiedProductVersion="15.0.2000.5"
  DTS:LocaleID="1033"
  DTS:ObjectName="{PACKAGE}"
  DTS:PackageType="5"
  DTS:VersionBuild="1"
  DTS:VersionGUID="{guid('version1')}">
  <DTS:Property
    DTS:Name="PackageFormatVersion">8</DTS:Property>
  <DTS:Variables>
{var_xml}
  </DTS:Variables>
  <DTS:Executables>
{exec_xml}
  </DTS:Executables>
  <DTS:PrecedenceConstraints>
{pc_xml}
  </DTS:PrecedenceConstraints>
  <DTS:DesignTimeProperties><![CDATA[{layout_xml(names)}]]></DTS:DesignTimeProperties>
</DTS:Executable>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT} ({len(tasks())} tasks)")


if __name__ == "__main__":
    main()
