param([Parameter(Mandatory=$true)][string]$FijiRoot)
$ErrorActionPreference='Stop'
$jdkBin = Get-ChildItem -LiteralPath (Join-Path $FijiRoot 'java') -Filter javac.exe -Recurse | Select-Object -First 1 -ExpandProperty DirectoryName
$ijJar = Get-ChildItem -LiteralPath (Join-Path $FijiRoot 'jars') -Filter 'ij-*.jar' | Select-Object -First 1 -ExpandProperty FullName
$gsonJar = Get-ChildItem -LiteralPath (Join-Path $FijiRoot 'jars') -Filter 'gson-*.jar' | Select-Object -First 1 -ExpandProperty FullName
$hf4Jar = Join-Path $FijiRoot 'plugins/cavity-light-hf4.jar'
if (-not $jdkBin -or -not $ijJar -or -not $gsonJar -or -not (Test-Path -LiteralPath $hf4Jar)) { throw 'Fiji debe incluir JDK, ImageJ, Gson y cavity-light-hf4.jar.' }
$buildDir=Join-Path $PSScriptRoot 'build'
if (Test-Path -LiteralPath $buildDir) { Remove-Item -LiteralPath $buildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$classPath=$ijJar+';'+$hf4Jar+';'+$gsonJar
$sources=@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.java' | Where-Object { $_.Name -notlike '*Test.java' } | ForEach-Object { $_.FullName })
& (Join-Path $jdkBin 'javac.exe') --release 8 -Xlint:-options -encoding UTF-8 -cp $classPath -d $buildDir @sources
if($LASTEXITCODE -ne 0){throw 'La compilacion fallo.'}
& (Join-Path $jdkBin 'jar.exe') cf (Join-Path $PSScriptRoot 'cavity-light-individual.jar') -C $buildDir cavity/light
if($LASTEXITCODE -ne 0){throw 'El empaquetado fallo.'}
$testBuild=Join-Path $PSScriptRoot 'test_build'
if (Test-Path -LiteralPath $testBuild) { Remove-Item -LiteralPath $testBuild -Recurse -Force }
New-Item -ItemType Directory -Force -Path $testBuild | Out-Null
$testSources=@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*Test.java' | ForEach-Object { $_.FullName })
& (Join-Path $jdkBin 'javac.exe') --release 8 -Xlint:-options -encoding UTF-8 -cp ($classPath+';'+$buildDir) -d $testBuild @testSources
if($LASTEXITCODE -ne 0){throw 'La compilacion de comprobaciones fallo.'}
& (Join-Path $jdkBin 'java.exe') '-Djava.awt.headless=true' -cp ($classPath+';'+$buildDir+';'+$testBuild) cavity.light.IndividualEditorTest (Join-Path $FijiRoot 'macros/toolsets/Cavity_TEM_Light_1_2_RC1.ijm')
if($LASTEXITCODE -ne 0){throw 'Las comprobaciones fallaron.'}
foreach ($testName in @('WorkspaceTest','ImagePreparationTest','RevisionWorkspaceTest','DetectorAssistantTest')) {
    & (Join-Path $jdkBin 'java.exe') '-Djava.awt.headless=true' -cp ($classPath+';'+$buildDir+';'+$testBuild) ('cavity.light.'+$testName)
    if($LASTEXITCODE -ne 0){throw ('Fallo '+$testName)}
}
