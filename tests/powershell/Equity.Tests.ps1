# Pester 5 tests of the command-line entry points, run on Windows by the ci workflow
# (job windows). They prove the CLIs start, read the repo's config and write what callers parse
# (JSON, the CI-checked gaps report) the same way on Windows as on Linux.
#
#   Invoke-Pester -Path tests/powershell -CI -Output Detailed

BeforeAll {
    $Repo = Resolve-Path (Join-Path $PSScriptRoot '..' '..')
    Push-Location $Repo
    # Python writes UTF-8 and PowerShell reads it as UTF-8 (the report has non-ASCII dashes).
    $env:PYTHONUTF8 = '1'
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    function Invoke-Equity([string[]]$Arguments) {
        $out = & uv run --locked python @Arguments 2>$null
        [pscustomobject]@{ Code = $LASTEXITCODE; Text = ($out -join "`n") }
    }
}

AfterAll { Pop-Location }

Describe 'gaps report' {
    It 'is generated without error and matches docs/gaps.md' {
        $r = Invoke-Equity @('-m', 'equity.gaps')
        $r.Code | Should -Be 0
        $expected = (Get-Content -Raw -Path 'docs/gaps.md') -replace "`r`n", "`n"
        $r.Text.TrimEnd() | Should -Be $expected.TrimEnd()
    }
}

Describe 'match runs' {
    It 'lists the sources of the DC run as JSON' {
        $r = Invoke-Equity @('-m', 'equity.matching.resolve', '--state', 'DC', '--list-sources')
        $r.Code | Should -Be 0
        $got = $r.Text | ConvertFrom-Json
        $got.sources | Should -Contain 'dc.statewide.parcels'
        $got.sources | Should -Contain 'dc.otr.delinquent_taxes'
        $got.sources | Should -Contain 'us.sba.ppp_chargeoffs'
    }

    It 'refuses a state that has no run' {
        $r = Invoke-Equity @('-m', 'equity.matching.resolve', '--state', 'ZZ', '--list-sources')
        $r.Code | Should -Not -Be 0
    }
}

Describe 'PACER budget guard' {
    It 'reports an unset ceiling and no requests on an empty ledger' {
        $ledger = Join-Path ([System.IO.Path]::GetTempPath()) ("pacer-" + [guid]::NewGuid() + '.jsonl')
        $r = Invoke-Equity @('-m', 'equity.pacer', 'status', '--ledger', $ledger)
        $r.Code | Should -Be 0
        $got = $r.Text | ConvertFrom-Json
        $got.ceiling | Should -BeNullOrEmpty
        $got.requests | Should -Be 0
        Test-Path $ledger | Should -BeFalse  # a status read never creates the ledger
    }
}

Describe 'unit tests on Windows' {
    It 'passes the matcher, lien adapter and reliability tests' {
        & uv run --locked pytest -q -p no:cacheprovider `
            tests/test_reliability.py tests/test_resolve.py tests/test_transfers.py `
            tests/test_scoring.py tests/test_pacer.py tests/adapters/test_liens.py `
            tests/adapters/test_sba_ppp.py
        $LASTEXITCODE | Should -Be 0
    }
}
