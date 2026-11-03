"""Plot audited checkpoint costs with ReportLab's standard LinePlot chart."""
import argparse
import json
from pathlib import Path
from reportlab.graphics.shapes import Drawing, String, Line, Rect
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics import renderSVG
from reportlab.lib import colors


def main(source, output):
    data = json.loads(source.read_text())
    assert data['all_record_checks_passed']
    palette = ['#374151', '#2563eb', '#0f977b', '#d97706', '#9333ea']
    conditions = ['A', 'B1', 'B2', 'B3', 'B4']
    labels = ['A: naive', 'B1: structure', 'B2: goal-local simp',
              'B3: one follow-up', 'B4: goal-first lemma']
    drawing = Drawing(880, 370)
    drawing.add(Rect(0, 0, 880, 370, fillColor=colors.white, strokeColor=None))
    drawing.add(String(28, 342, 'P01: A + one instruction per B',
                       fontName='Helvetica-Bold', fontSize=17))
    drawing.add(String(28, 321, 'Best observed cost; lower is better. Mean of two independent runs.',
                       fontSize=10, fillColor=colors.HexColor('#4b5563')))
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 62, 83, 435, 204
    plot.data = [[(k, data['aggregate'][c]['checkpoints'][str(k)]['mean_cost'])
                  for k in [3, 6, 10]] for c in conditions]
    plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 3, 10
    plot.xValueAxis.valueSteps = [3, 6, 10]
    plot.yValueAxis.valueMin = 0
    plot.yValueAxis.labelTextFormat = '%.2f'
    plot.yValueAxis.visibleGrid = True
    plot.yValueAxis.gridStrokeColor = colors.HexColor('#e5e7eb')
    for i, color in enumerate(palette):
        plot.lines[i].strokeColor = colors.HexColor(color)
        plot.lines[i].strokeWidth = 1.8
        plot.lines[i].symbol = makeMarker('FilledCircle')
        plot.lines[i].symbol.size = 5
    drawing.add(plot)
    drawing.add(String(162, 51, 'Completed proposals (total budget = 10)', fontSize=10))
    drawing.add(String(22, 293, 'Cost', fontSize=10))
    for i, (label, color) in enumerate(zip(labels, palette)):
        y = 280 - i * 40
        drawing.add(Line(540, y+3, 558, y+3, strokeWidth=2,
                         strokeColor=colors.HexColor(color)))
        drawing.add(String(566, y, label, fontName='Helvetica-Bold', fontSize=10))
        row = data['aggregate'][conditions[i]]
        values = ' / '.join(f"{row['checkpoints'][str(k)]['mean_cost']:.4f}" for k in [3, 6, 10])
        drawing.add(String(566, y-13, values + f"    final pass {row['final_valid_count']}/2",
                           fontSize=9, fillColor=colors.HexColor('#4b5563')))
    drawing.add(String(540, 304, 'Mean cost at 3 / 6 / 10 proposals', fontSize=10))
    drawing.add(String(28, 27, 'Search-time measurements. Final revalidation is reported separately. Two repetitions do not establish significance.',
                       fontSize=8.5, fillColor=colors.HexColor('#4b5563')))
    output.parent.mkdir(parents=True, exist_ok=True)
    renderSVG.drawToFile(drawing, str(output.with_suffix('.svg')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output_stem', type=Path)
    args = parser.parse_args()
    main(args.source.resolve(), args.output_stem.resolve())
