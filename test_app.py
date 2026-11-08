from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest

at=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=600).run()
assert not at.exception, [x.message for x in at.exception]
assert not at.error, [x.value for x in at.error]
assert not at.warning, [x.value for x in at.warning]
assert at.metric[0].value=='8,760'
assert len(at.dataframe[1].value)==12
print('INITIAL METRICS',[(x.label,x.value) for x in at.metric],flush=True)
for d in [date(2026,1,1),date(2026,3,8),date(2026,11,1),date(2026,12,31)]:
    at.date_input[0].set_value(d).run()
    assert not at.exception and not at.error
    assert len(at.dataframe[0].value) in (3,4,5)
    print('DAILY PASS',d,len(at.dataframe[0].value),flush=True)
for direction,threshold,expected in [('At or above',100.,0),('At or below',100.,8760),('At or above',-100.,8760),('At or below',-100.,0)]:
    at.radio[0].set_value(direction)
    at.number_input[0].set_value(threshold).run()
    assert not at.exception and not at.error
    assert int(at.metric[3].value.replace(',',''))==expected
    assert int(at.dataframe[2].value['hours'].sum())==expected
    print('THRESHOLD PASS',direction,threshold,expected,flush=True)
print('ALL APP TESTS PASSED',flush=True)
