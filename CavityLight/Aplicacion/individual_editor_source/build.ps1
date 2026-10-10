param([Parameter(Mandatory=$true)][string]$FijiRoot)
$ErrorActionPreference='Stop'
$jdkBin = Get-ChildItem -LiteralPath (Join-Path $FijiRoot 'java') -Filter javac.exe -Recurse | Select-Object -First 1 -ExpandProperty DirectoryName
$ijJar = Get-ChildItem -LiteralPath (Join-Path $FijiRoot 'jars') -Filter 'ij-*.jar' | Select-Object -First 1 -ExpandProperty FullName
if (-not $jdkBin -or -not $ijJar) { throw 'Fiji debe incluir el JDK y ij.jar.' }
$buildDir=Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$classPath=$ijJar+';'+(Join-Path $PSScriptRoot 'cavity-light-hf4.jar')
& (Join-Path $jdkBin 'javac.exe') --release 8 -Xlint:-options -encoding UTF-8 -cp $classPath -d $buildDir (Join-Path $PSScriptRoot 'IndividualEditor.java')
if($LASTEXITCODE -ne 0){throw 'La compilacion fallo.'}
& (Join-Path $jdkBin 'jar.exe') cf (Join-Path $PSScriptRoot 'cavity-light-individual.jar') -C $buildDir cavity/light
if($LASTEXITCODE -ne 0){throw 'El empaquetado fallo.'}
$testBuild=Join-Path $PSScriptRoot 'test_build'
New-Item -ItemType Directory -Force -Path $testBuild | Out-Null
& (Join-Path $jdkBin 'javac.exe') --release 8 -Xlint:-options -encoding UTF-8 -cp ($classPath+';'+$buildDir) -d $testBuild (Join-Path $PSScriptRoot 'IndividualEditorTest.java')
if($LASTEXITCODE -ne 0){throw 'La compilacion de comprobaciones fallo.'}
& (Join-Path $jdkBin 'java.exe') '-Djava.awt.headless=true' -cp ($classPath+';'+$buildDir+';'+$testBuild) cavity.light.IndividualEditorTest (Join-Path $PSScriptRoot 'Cavity_TEM_Light_1_2_RC1.ijm')
if($LASTEXITCODE -ne 0){throw 'Las comprobaciones fallaron.'}
