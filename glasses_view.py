# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Lightweight 3D glasses mesh, projected onto a Tk canvas without a GPU dependency."""
import math
import tkinter as tk
from app_theme import BACKGROUND, MUTED, SUCCESS, WARNING, GUIDE


def rotate(point, yaw, pitch, roll):
    # Positive display angles: look right, look up, tilt right.
    x, y, z = point
    a, b, c = map(math.radians, (yaw, -pitch, -roll))
    x, y = x * math.cos(c) - y * math.sin(c), x * math.sin(c) + y * math.cos(c)
    y, z = y * math.cos(b) - z * math.sin(b), y * math.sin(b) + z * math.cos(b)
    return x * math.cos(a) + z * math.sin(a), y, -x * math.sin(a) + z * math.cos(a)


def box(x0, x1, y0, y1, z0, z1, color):
    vertices = [(x0,y0,z0), (x1,y0,z0), (x1,y1,z0), (x0,y1,z0),
                (x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1)]
    return [([vertices[i] for i in indices], color) for indices in
            ((0,3,2,1), (4,5,6,7), (0,1,5,4), (3,7,6,2), (0,4,7,3), (1,2,6,5))]


def mesh():
    faces = []
    frame = '#ffffff'
    for sign in (-1, 1):
        center = sign * 0.66
        # Rounded rectangular rims with real depth and open lens centers.
        outer = [(-.55,.19),(-.43,.34),(.43,.34),(.55,.19),(.51,-.22),(.36,-.34),(-.36,-.34),(-.51,-.22)]
        inner = [(x*.81, y*.74) for x,y in outer]
        for i in range(8):
            j = (i+1)%8
            def p(ring, k, depth):
                x,y = ring[k]
                return center+x,y,depth
            faces += [([p(outer,i,.64),p(outer,j,.64),p(inner,j,.64),p(inner,i,.64)],frame),
                      ([p(outer,j,.48),p(outer,i,.48),p(inner,i,.48),p(inner,j,.48)],frame),
                      ([p(outer,i,.48),p(outer,j,.48),p(outer,j,.64),p(outer,i,.64)],frame),
                      ([p(inner,j,.48),p(inner,i,.48),p(inner,i,.64),p(inner,j,.64)],frame)]
        faces.append(([(center+x,y,.565) for x,y in inner], '#648393'))
        faces.append(([(center-.29,.13,.575),(center-.22,.21,.575),
                       (center+.24,.21,.575),(center+.17,.13,.575)], '#91a8b5'))
        # Temples and earpieces extend behind the face, making rotation easy to see.
        x = sign*1.16
        faces += box(x-.065,x+.065,.10,.29,-.94,.55,frame)
        faces += box(x-.07,x+.07,-.12,.20,-1.10,-.88,frame)
        faces += box(x-.075,x+.075,.12,.26,-.35,.18,'#f0f0f0')
    faces += box(-.17,.17,.14,.25,.49,.64,frame)
    faces += box(-.075,.075,.07,.20,.48,.61,frame)
    return faces


MESH = mesh()


def view_point(point, pose):
    # At rest the wearer looks into the screen (-Z); camera is behind the wearer.
    # Change the display basis as well as the mesh so right/up/roll remain intuitive.
    x,y,z = point
    yaw,pitch,roll = pose
    # Display-only roll correction for the Rokid sensor basis. Game output is unchanged.
    return rotate((-x,y,-z), -yaw,-pitch,-roll)


def project(point, width, height):
    x,y,z = point
    scale = min(width/4.5,height/3.7)
    return width*.5+x*scale*6/(6-z),height*.46-y*scale*6/(6-z)


def scene(pose, width, height):
    polygons = []
    for points, color in MESH:
        rotated = [view_point(p, pose) for p in points]
        screen = [project(p,width,height) for p in rotated]
        a,b,c = rotated[:3]
        u,v = [b[i]-a[i] for i in range(3)],[c[i]-a[i] for i in range(3)]
        normal = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        length = math.sqrt(sum(n*n for n in normal)) or 1
        light = .65+.35*abs((normal[0]*-.3+normal[1]*.6+normal[2]*.74)/length)
        rgb = [min(255, int(int(color[i:i+2],16)*light)) for i in (1,3,5)]
        polygons.append((sum(p[2] for p in rotated)/len(rotated), screen, '#%02x%02x%02x'%tuple(rgb)))
    return sorted(polygons,key=lambda face:face[0])


class GlassesView(tk.Canvas):
    def __init__(self, parent, translate=lambda text: text):
        super().__init__(parent, height=180, width=280, background=BACKGROUND,
                         highlightthickness=0, borderwidth=0)
        self.pose = (0.,0.,0.)
        self.translate = translate
        self.active = False
        self.message = 'Chưa kết nối kính'
        self.message_color = MUTED
        self.bind('<Configure>', lambda event:self.draw())

    def update_pose(self, pose, active, message=None, paused=False):
        self.pose = tuple(pose) if active else (0.,0.,0.)
        self.active = active
        self.message = message or ('Đang theo dõi đầu' if active else 'Đang chờ kính sẵn sàng')
        self.message_color = WARNING if paused else SUCCESS if active else MUTED
        self.draw()

    def draw(self):
        width,height = max(1,self.winfo_width()), max(1,self.winfo_height())
        self.delete('all')
        center_x,center_y = project((0,0,0),width,height)
        # A fixed reference cross remains level while the model moves.
        self.create_line(width*.12,center_y,width*.88,center_y,fill=GUIDE,width=1)
        self.create_line(center_x,28,center_x,height-34,fill=GUIDE,width=1)
        for x,y in ((center_x,center_y),(center_x-30,center_y),(center_x+30,center_y)):
            self.create_line(x,center_y-3,x,center_y+3,fill=GUIDE)
        for _, points, color in scene(self.pose,width,height):
            self.create_polygon(*[v for p in points for v in p],fill=color,outline=color)
        self.create_text(width/2,height-14,text=self.translate(self.message),
                         fill=self.message_color,font=('Segoe UI',10))
