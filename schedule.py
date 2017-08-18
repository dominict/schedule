#!/usr/bin/python3
__requires__ = ['attrs~=17.1', 'click~=6.5', 'reportlab']
from   collections.abc           import Mapping
from   datetime                  import time
from   math                      import ceil, floor
import re
from   textwrap                  import wrap
import attr
import click
from   reportlab.lib             import pagesizes
from   reportlab.lib.units       import inch
from   reportlab.pdfbase         import pdfmetrics
from   reportlab.pdfbase.ttfonts import TTFont
from   reportlab.pdfgen.canvas   import Canvas

EM = 0.6  ### TODO: Eliminate

WEEKDAYS_EN  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
FULL_WEEK_EN = ['Sunday'] + WEEKDAYS_EN + ['Saturday']

DAY_REGEXES = [
    ('Monday', '[Mm]'),
    ('Tuesday', '[Tt]'),
    ('Wednesday', '[Ww]'),
    ('Thursday', '[HhRr]'),
    ('Friday', '[Ff]'),
]

GREY = (0.8, 0.8, 0.8)

COLORS = [
    GREY,
    (1,   0,   0),    # red
    (0,   1,   0),    # blue
    (0,   0,   1),    # green
    (0,   1,   1),    # cyan
    (1,   1,   0),    # yellow
    (0.5, 0,   0.5),  # purple
    (1,   1,   1),    # white
    (1,   0.5, 0),    # orange
    (1,   0,   1),    # magenta
]

class Schedule:
    def __init__(self, days, day_names=None):
        self.events = []
        self.days = list(days)
        if day_names is None:
            self._day_names = lambda d: d
        elif isinstance(day_names, Mapping):
            self._day_names = day_names.__getitem__
        elif not callable(day_names):
            raise TypeError('day_names must be a callable or dict')
        else:
            self._day_names = day_names

    def add_event(self, event):
        ### TODO: Warn if the event references any unknown days?
        self.events.append(event)

    def day_names(self):
        return map(self._day_names, self.days)

    def all_events(self):
        return self.events

    def events_on_day(self, day):
        return [e for e in self.events if day in e.days]

    @property
    def number_of_days(self):
        return len(self.days)

    # The font and pagesize of the canvas must already have been set
    # x,y: upper-left corner of schedule to render (counting times along the
    # edge; `render` should not draw anything outside the given box)
    def render(self, canvas, width, height, x, y, font_size, show_times=True,
                     min_time=None, max_time=None):
        if min_time is None:
            min_time = max(min(time2hours(ev.start_time)
                               for ev in self.all_events()) - 0.5, 0)
        if max_time is None:
            max_time = min(max(time2hours(ev.end_time)
                               for ev in self.all_events()) + 0.5, 24)
        # Hours to label and draw a line across
        hours = range(floor(min_time) + 1, ceil(max_time))
        line_height = font_size * 1.2
        # Font size of the day headers at the top of each column:
        header_size = font_size * 1.2
        # Height of the boxes in which the day headers will be drawn:
        day_height = header_size * 1.2
        # Font size of the time labels at the left of each hour:
        time_size = font_size / 1.2
        # Boundaries of where this method is allowed to draw stuff:
        area = Box(x, y, width, height)

        canvas.setFontSize(time_size)
        # Gap between the right edge of the time labels and the left edge of
        # the schedule box.  I don't remember how I came up with this formula.
        time_gap = 0.2 * canvas.stringWidth(':00')
        if show_times:
            time_width = time_gap + max(
                canvas.stringWidth('{}:00'.format(i)) for i in hours
            )
        else:
            time_width = 0

        sched = Box(
            x + time_width,
            y - day_height,
            width - time_width,
            height - day_height,
        )
        hour_height = sched.height / (max_time - min_time)
        day_width = sched.width / self.number_of_days
        line_width = floor(day_width / (font_size * EM))

        # Border around schedule and day headers:
        canvas.rect(sched.ulx, sched.lry, sched.width, area.height)

        # Day headers text:
        canvas.setFontSize(header_size)
        for i, day in enumerate(self.day_names()):
            canvas.drawCentredString(
                sched.ulx + day_width * (i + 0.5),
                area.uly - line_height,
                day,
            )

        # Underline beneath day headers:
        canvas.line(sched.ulx, sched.uly, sched.lrx, sched.uly)

        # Lines across each hour:
        canvas.setDash([2], 0)
        for i in hours:
            y = sched.uly - (i - min_time) * hour_height
            canvas.line(sched.ulx, y, sched.lrx, y)

        # Lines between each day:
        canvas.setDash([], 0)
        for i in range(1, self.number_of_days):
            x = sched.ulx + i * day_width
            canvas.line(x, area.uly, x, area.lry)

        if show_times:
            canvas.setFontSize(time_size)
            for i in hours:
                canvas.drawRightString(
                    sched.ulx - time_gap,
                    sched.uly - (i-min_time)*hour_height - time_size/2,
                    '{}:00'.format(i),
                )

        # Events:
        canvas.setFontSize(font_size)
        for i, day in enumerate(self.days):
            dx = sched.ulx + day_width * i
            for ev in self.events_on_day(day):
                ebox = Box(
                    dx,
                    sched.uly-(time2hours(ev.start_time)-min_time)*hour_height,
                    day_width,
                    ev.length * hour_height,
                )
                # Event box:
                canvas.setStrokeColorRGB(0,0,0)
                canvas.setFillColorRGB(*ev.color)
                canvas.rect(*ebox.rect(), stroke=1, fill=1)
                canvas.setFillColorRGB(0,0,0)

                # Event text:
                ### TODO: Use PLATYPUS or whatever for this part:
                text = sum((wrap(t, line_width) for t in ev.text), [])
                tmp_size = None
                if len(text) * line_height > ebox.height:
                    tmp_size = ebox.height / len(text) / 1.2
                    canvas.setFontSize(tmp_size)
                    line_height = tmp_size * 1.2
                y = ebox.lry + ebox.height / 2 + len(text) * line_height / 2
                for t in text:
                    y -= line_height
                    canvas.drawCentredString(ebox.ulx + day_width/2, y, t)
                if tmp_size is not None:
                    canvas.setFontSize(font_size)
                    line_height = font_size * 1.2


@attr.s
class Event:
    start_time = attr.ib(validator=attr.validators.instance_of(time))
    end_time   = attr.ib(validator=attr.validators.instance_of(time))
    text       = attr.ib()
    color      = attr.ib()
    days       = attr.ib()  # List of days

    def __attrs_post_init__(self):
        if self.start_time >= self.end_time:
            raise ValueError('Event must start before it ends')

    @property
    def length(self):
        """ The length of the event in hours """
        return timediff(self.start_time, self.end_time)


@attr.s
class Box:
    ulx    = attr.ib()
    uly    = attr.ib()
    width  = attr.ib()
    height = attr.ib()

    @property
    def lrx(self):
        return self.ulx + self.width

    @property
    def lry(self):
        return self.uly - self.height

    def rect(self):
        return (self.ulx, self.lry, self.width, self.height)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option('-C', '--color', is_flag=True)
@click.option('-F', '--font')
@click.option('-f', '--font-size', type=float, default=10)
@click.option('-p', '--portrait', is_flag=True)
@click.option('-s', '--scale', type=float)
@click.option('-T', '--no-times', is_flag=True)
@click.argument('infile', type=click.File(), default='-')
@click.argument('outfile', type=click.File('wb'), default='-')
def main(infile, outfile, color, font, font_size, portrait, scale, no_times):
    if font is not None:
        font_name = 'CustomFont'
        ### TODO: Use the basename of the filename as the font name?  (Could
        ### that ever cause problems?)
        pdfmetrics.registerFont(TTFont(font_name, font))
    else:
        font_name = 'Helvetica'
    if portrait:
        page_width, page_height = pagesizes.portrait(pagesizes.letter)
    else:
        page_width, page_height = pagesizes.landscape(pagesizes.letter)
    colors = COLORS if color else [GREY]
    sched = Schedule(WEEKDAYS_EN)
    for i, line in enumerate(infile):
        line = line.rstrip('\r\n').partition('#')[0]
        if not line.strip():
            continue
        days, timestr, *text = line.split('\t')
        m = re.match(r'^\s*(\d{1,2})(?:[:.]?(\d{2}))?\s*'
                     r'-\s*(\d{1,2})(?:[:.]?(\d{2}))?\s*$', timestr)
        if not m:
            click.echo('Invalid time: ' + repr(timestr), err=True)
            continue
        start = time(int(m.group(1)), int(m.group(2) or 0))
        end   = time(int(m.group(3)), int(m.group(4) or 0))
        sched.add_event(Event(
            start_time = start,
            end_time   = end,
            text       = text,
            color      = colors[i % len(colors)],
            days       = [d for d,rgx in DAY_REGEXES if re.search(rgx, days)],
        ))
    c = Canvas(outfile, (page_width, page_height))
    c.setFont(font_name, font_size)
    if scale is not None:
        factor = 1 / scale
        c.translate(
            (1-factor) * page_width / 2,
            (1-factor) * page_height / 2,
        )
        c.scale(factor, factor)
    sched.render(
        c,
        x          = inch,
        y          = page_height - inch,
        width      = page_width - 2*inch,
        height     = page_height - 2*inch,
        font_size  = font_size,
        show_times = not no_times,
    )
    c.showPage()
    c.save()

def time2hours(t):
    return t.hour + (t.minute + (t.second + t.microsecond/1000000)/60)/60

def timediff(t1, t2):
    # Returns the difference between two `datetime.time` objects as a number of
    # hours
    return time2hours(t2) - time2hours(t1)

if __name__ == '__main__':
    main()
