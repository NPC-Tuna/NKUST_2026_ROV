#   🔴 Red face = Forward
#   🟢 Green face = Back

import pygame
import math
import random
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# =========================
# Init
# =========================
pygame.init()
pygame.joystick.init()

joystick = pygame.joystick.Joystick(0)
joystick.init()

screen = pygame.display.set_mode((900, 700), DOUBLEBUF | OPENGL)
pygame.display.set_caption("ROV Control Viewer")

glEnable(GL_DEPTH_TEST)
glClearColor(0.0, 0.1, 0.2, 1.0)

# =========================
# Fog
# =========================
glEnable(GL_FOG)
glFogfv(GL_FOG_COLOR, (GLfloat * 4)(0.0, 0.15, 0.25, 1.0))
glFogf(GL_FOG_START, 5.0)
glFogf(GL_FOG_END, 35.0)
glFogi(GL_FOG_MODE, GL_LINEAR)

# =========================
# Particles
# =========================
particles = []
for _ in range(250):
    particles.append([
        random.uniform(-30, 30),
        random.uniform(-15, 15),
        random.uniform(-40, 10)
    ])

def draw_particles():
    glPointSize(2)
    glBegin(GL_POINTS)
    glColor3f(0.8, 0.9, 1.0)
    for p in particles:
        glVertex3f(p[0], p[1], p[2])
        p[1] += 0.01
        if p[1] > 15:
            p[1] = -15
    glEnd()

# =========================
# Background
# =========================
def draw_background():
    glDisable(GL_DEPTH_TEST)

    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(-1, 1, -1, 1, -1, 1)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glBegin(GL_QUADS)
    glColor3f(0.0, 0.35, 0.55)
    glVertex2f(-1,  1)
    glVertex2f( 1,  1)
    glColor3f(0.0, 0.05, 0.15)
    glVertex2f( 1, -1)
    glVertex2f(-1, -1)
    glEnd()

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

    glEnable(GL_DEPTH_TEST)

# =========================
# Draw ROV
# =========================
def draw_rov():
    w, h, d = 2.5, 1.0, 4.0
    glBegin(GL_QUADS)

    glColor3f(1, 0, 0)
    glVertex3f(-w, -h,  d)
    glVertex3f( w, -h,  d)
    glVertex3f( w,  h,  d)
    glVertex3f(-w,  h,  d)

    glColor3f(0, 1, 0)
    glVertex3f(-w, -h, -d)
    glVertex3f( w, -h, -d)
    glVertex3f( w,  h, -d)
    glVertex3f(-w,  h, -d)

    glColor3f(1, 1, 0)
    glVertex3f(-w, -h, -d)
    glVertex3f(-w, -h,  d)
    glVertex3f(-w,  h,  d)
    glVertex3f(-w,  h, -d)

    glColor3f(0, 0, 1)
    glVertex3f(w, -h, -d)
    glVertex3f(w, -h,  d)
    glVertex3f(w,  h,  d)
    glVertex3f(w,  h, -d)

    glColor3f(0.6, 0.2, 1)
    glVertex3f(-w, h, -d)
    glVertex3f( w, h, -d)
    glVertex3f( w, h,  d)
    glVertex3f(-w, h,  d)

    glColor3f(0.5, 0.5, 0.5)
    glVertex3f(-w, -h, -d)
    glVertex3f( w, -h, -d)
    glVertex3f( w, -h,  d)
    glVertex3f(-w, -h,  d)

    glEnd()

# =========================
# State
# =========================
x, y, z = 0.0, 0.0, 0.0
yaw = 0.0

# Camera position (world-fixed)
cam_x, cam_y, cam_z = 0.0, 5.0, -15.0

last_y_button = False

# =========================
# Main Loop
# =========================
clock = pygame.time.Clock()
running = True

while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == QUIT:
            running = False

    pygame.event.pump()

    lx = joystick.get_axis(0)
    ly = -joystick.get_axis(1)
    rx = joystick.get_axis(2)
    ry = -joystick.get_axis(3)
    y_button = joystick.get_button(3)

    speed = 0.12
    yaw_rad = math.radians(yaw)

    # ROV movement
    x += math.sin(yaw_rad) * ly * speed
    z += math.cos(yaw_rad) * ly * speed
    x += math.cos(yaw_rad) * lx * speed * -1
    z -= math.sin(yaw_rad) * lx * speed * -1
    y += ry * speed
    yaw += rx * -2.0

    # 📸 Camera teleport (ONE-SHOT)
    if y_button and not last_y_button:
        cam_dist = 12
        cam_height = 5
        cam_x = x - math.sin(yaw_rad) * cam_dist
        cam_z = z - math.cos(yaw_rad) * cam_dist
        cam_y = y + cam_height

    last_y_button = y_button

    # ================= DRAW =================
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    draw_background()

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, 900 / 700, 0.1, 100.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    gluLookAt(
        cam_x, cam_y, cam_z,
        x, y, z,
        0, 1, 0
    )

    draw_particles()

    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(yaw, 0, 1, 0)
    draw_rov()
    glPopMatrix()

    pygame.display.flip()

pygame.quit()