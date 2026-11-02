"""Plot audited means and observed run ranges with ReportLab LinePlot.

Use the bundled artifact Python runtime (ReportLab is already installed there).
These are search-time costs; final validity is reported separately.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import reportlab
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderSVG
from reportlab.lib import colors

PALETTE = {'S': '#374151', 'M': '#00877a'}
STEPS = [3, 6, 10]


def plot(data, pid, output):
    drawing = Drawing(720, 390)
    drawing.add(Rect(0, 0, 720, 390, fillColor=colors.white, strokeColor=None))
    drawing.add(String(28, 359, f'{pid}: structured extraction vs model summary',
                       fontName='Helvetica-Bold', fontSize=17))
    drawing.add(String(28, 338, 'Best observed cost; lower is better. Two independent runs per condition.',
                       fontSize=10, fillColor=colors.HexColor('#4b5563')))
    groups = data['aggregate'][pid]
    upper = max(groups[c]['checkpoints'][str(k)]['max_cost'] for c in PALETTE for k in STEPS)
    tick = 0.2 if upper >= 0.6 else 0.1 if upper >= 0.25 else 0.05
    ymax = max(tick, math.ceil(upper * 1.10 / tick) * tick)
    chart = LinePlot()
    chart.x, chart.y, chart.width, chart.height = 62, 92, 430, 222
    chart.data = [[(k, groups[c]['checkpoints'][str(k)]['mean_cost']) for k in STEPS] for c in PALETTE]
    chart.xValueAxis.valueMin, chart.xValueAxis.valueMax = 3, 10
    chart.xValueAxis.rangeRound = 'none'
    chart.xValueAxis.valueSteps = STEPS
    chart.yValueAxis.valueMin, chart.yValueAxis.valueMax = 0, ymax
    chart.yValueAxis.rangeRound = 'none'
    chart.yValueAxis.valueSteps = [round(i * tick, 10) for i in range(round(ymax / tick) + 1)]
    chart.yValueAxis.labelTextFormat = '%.2f'
    chart.yValueAxis.visibleGrid = True
    chart.yValueAxis.gridStrokeColor = colors.HexColor('#e5e7eb')
    for index, condition in enumerate(PALETTE):
        line = chart.lines[index]
        line.strokeColor = colors.HexColor(PALETTE[condition])
        line.strokeWidth = 1.8
        line.symbol = makeMarker('FilledCircle')
        line.symbol.size = 5
    drawing.add(chart.draw())
    # Annotate the standard linear chart with observed min/max, not confidence
    # intervals. Use the configured standard chart axes for the projection.
    for index, condition in enumerate(PALETTE):
        color = colors.HexColor(PALETTE[condition])
        group = groups[condition]
        for step in STEPS:
            value = group['checkpoints'][str(step)]
            assert 0 <= value['min_cost'] <= value['mean_cost'] <= value['max_cost'] <= ymax
            x = chart.xValueAxis.scale(step)
            low = chart.yValueAxis.scale(value['min_cost'])
            high = chart.yValueAxis.scale(value['max_cost'])
            for x1, y1, x2, y2 in [(x, low, x, high), (x-3, low, x+3, low), (x-3, high, x+3, high)]:
                drawing.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1))
        y = 283 - index * 85
        label = 'S: structured extraction' if condition == 'S' else 'M: model summary'
        drawing.add(Line(521, y+3, 539, y+3, strokeColor=color, strokeWidth=2))
        drawing.add(String(546, y, label, fontName='Helvetica-Bold', fontSize=9.5))
        for offset, step in enumerate(STEPS):
            value = group['checkpoints'][str(step)]
            drawing.add(String(521, y-17-13*offset,
                f'{step:2d}: {value["mean_cost"]:.4f} [{value["min_cost"]:.4f}, {value["max_cost"]:.4f}]',
                fontSize=8.5, fillColor=colors.HexColor('#4b5563')))
    drawing.add(String(27, 317, 'Cost', fontSize=10))
    drawing.add(String(152, 53, 'Completed proposals (total budget = 10)', fontSize=10))
    drawing.add(String(28, 27, 'Points/lines: mean. Bars: min-max of two runs, not confidence intervals.',
                       fontSize=9, fillColor=colors.HexColor('#4b5563')))
    drawing.add(String(28, 12, 'Search-time observations; final validation is separate. Two repetitions do not establish significance.',
                       fontSize=8.5, fillColor=colors.HexColor('#4b5563')))
    bounds = drawing.getBounds()
    assert bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= 720 and bounds[3] <= 390, bounds
    renderSVG.drawToFile(drawing, str(output))


def main(source, destination):
    data = json.loads(source.read_text())
    assert data['all_record_checks_passed'] and data['trial_count'] == 8
    destination.mkdir(parents=True, exist_ok=True)
    outputs = []
    for pid in ['P01', 'P13']:
        output = destination / f'{pid}-cost-ranges.svg'
        plot(data, pid, output)
        outputs.append(output)
    metadata = {'source_summary_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'library': 'ReportLab ' + reportlab.Version,
                'range_definition': 'Observed min/max of two independent runs; not confidence interval',
                'files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs}}
    (destination / 'plots-provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'plotted': [p.name for p in outputs]}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    main(args.source.resolve(), args.destination.resolve())
