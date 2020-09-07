"""Yolo image annotation tool"""
from __future__ import division
import os
import sys
import glob
from pathlib import Path
from tkinter import Tk, filedialog, Frame, Label, Entry, Button, Canvas, StringVar, OptionMenu
from tkinter import messagebox as tkMessageBox
from tkinter import Listbox, LEFT, RIGHT, TOP, END, BOTH, N, E, W, S, NW
from PIL import Image as PImage, ImageTk

TK_SILENCE_DEPRECATION = 1

MAIN_COLOURS = ['darkseagreen', 'darkorange',
                'darkturquoise', 'darkgreen',
                'darkviolet', 'darkgray', 'darkmagenta',
                'darkblue', 'darkkhaki', 'darkcyan', 'darkred',
                'darksalmon', 'darkgoldenrod',
                'darkgrey', 'darkslateblue', 'darkorchid',
                'skyblue', 'yellow', 'orange', 'red', 'pink',
                'violet', 'green', 'brown', 'gold', 'Olive',
                'Maroon', 'blue', 'cyan', 'black', 'olivedrab',
                'lightcyan', 'silver']

SIZE = 256, 256

SUPPORTED_IMAGE_TYPES = ('*.jpg', '*.png')
IMAGES_ROOT = Path("./Images").resolve()
IMAGES_ROOT.mkdir(parents=True, exist_ok=True)

CLASSES_FILENAME = 'classes.txt'
CLASSES = []

try:
    with open(CLASSES_FILENAME, 'r') as cls:
        CLASSES = cls.readlines()
    CLASSES = [cls.strip() for cls in CLASSES]
except IOError as error:
    print("[ERROR] Please create {0} and put your all classes".format(CLASSES_FILENAME))
    sys.exit(1)
assert len(CLASSES) <= len(MAIN_COLOURS)
COLOURS = MAIN_COLOURS[:len(CLASSES)]


def tl_br_bbox_to_yolo_bbox(tl_br_bbox):
    """Convert Top left (TL), bottom right (BR), format bounding box to YOLO format"""
    width = tl_br_bbox[2] - tl_br_bbox[0]
    height = tl_br_bbox[3] - tl_br_bbox[1]
    center_x = tl_br_bbox[0] + width/2
    center_y = tl_br_bbox[1] + height/2
    return (center_x, center_y, width, height)


def yolo_bbox_to_tl_br_bbox(yolo_bbox):
    """Convert YOLO format format bounding box to Top left (TL), bottom right (BR) format"""
    tl_x = yolo_bbox[0] - yolo_bbox[2]/2
    tl_y = yolo_bbox[1] - yolo_bbox[3]/2
    br_x = tl_x + yolo_bbox[2]
    br_y = tl_x + yolo_bbox[3]
    return (tl_x, tl_y, br_x, br_y)


def rel_bbox_to_abs_bbox(rel_bbox, img_size):
    """Convert relative (to image size) bounding box to absolute pixel bounding box"""
    return (rel_bbox[0]*img_size[0], rel_bbox[1]*img_size[1],
            rel_bbox[2]*img_size[0], rel_bbox[3]*img_size[1])


class LabelTool():
    """Simple YOLO format annotation tool based on tkinter"""

    def __init__(self, master):
        # set up the main frame
        self.curimg_h = 0
        self.curimg_w = 0
        self.cur_cls_id = -1
        self.parent = master
        self.parent.title("Yolo Annotation Tool")
        self.frame = Frame(self.parent)
        self.frame.pack(fill=BOTH, expand=1)
        self.parent.resizable(width=False, height=False)

        # initialise global state
        self.imageDir = ''
        self.imageList = []
        self.egDir = ''
        self.egList = []
        self.outDir = ''
        self.cur = 0
        self.total = 0
        self.category = 0
        self.imagename = ''
        self.labelfilename = ''
        self.tkimg = None
        self.img = None

        # initialise mouse state
        self.STATE = {}
        self.STATE['click'] = 0
        self.STATE['x'], self.STATE['y'] = 0, 0

        # reference to bbox
        self.bboxIdList = []
        self.bboxId = None
        self.bboxList = []
        self.bboxListCls = []
        self.hl = None
        self.vl = None

        # ----------------- GUI thing ---------------------
        # dir entry & load
        self.label = Label(self.frame, text="Image Dir:")
        self.label.grid(row=0, column=0, sticky=E)
        self.entry = Entry(self.frame)
        # self.entry.focus_set()
        #self.entry.bind('<Return>', self.loadEntry)
        self.entry.grid(row=0, column=1, sticky=W+E)
        self.ldBtn = Button(self.frame, text="Load", command=self.load_dir_dialog)
        self.ldBtn.grid(row=0, column=2, sticky=W+E)

        # main panel for labelling
        self.mainPanel = Canvas(self.frame, cursor='tcross')
        self.mainPanel.bind("<Button-1>", self.mouse_click)
        self.mainPanel.bind("<Motion>", self.mouse_move)
        self.mainPanel.bind("<Configure>", self.resize_image)
        self.parent.bind("<Escape>", self.cancel_bbox)  # press <Espace> to cancel current bbox
        self.parent.bind("s", self.cancel_bbox)
        self.parent.bind("<Left>", self.previous_image)  # press 'a' to go backforward
        self.parent.bind("<Right>", self.next_image)  # press 'd' to go forward
        self.mainPanel.grid(row=1, column=1, rowspan=4, sticky=W+N)

        # showing bbox info & delete bbox
        self.tkvar = StringVar(self.parent)
        self.cur_cls_id = 0
        self.tkvar.set(CLASSES[0])  # set the default option
        self.popupMenu = OptionMenu(self.frame, self.tkvar, *CLASSES, command=self.change_dropdown)
        self.popupMenu.grid(row=1, column=2, sticky=E+S)
        self.chooselbl = Label(self.frame, text='Choose Class:')
        self.chooselbl.grid(row=1, column=2, sticky=W+S)
        self.lb1 = Label(self.frame, text='Bounding boxes:')
        self.lb1.grid(row=2, column=2, sticky=W+N)
        self.listbox = Listbox(self.frame, width=30, height=12)
        self.listbox.grid(row=3, column=2, sticky=N)
        self.btnDel = Button(self.frame, text='Delete', command=self.delete_bbox)
        self.btnDel.grid(row=4, column=2, sticky=W+E+N)
        self.btnClear = Button(self.frame, text='ClearAll', command=self.clear_all_bbox)
        self.btnClear.grid(row=5, column=2, sticky=W+E+N)

        # control panel for image navigation
        self.ctrPanel = Frame(self.frame)
        self.ctrPanel.grid(row=6, column=1, columnspan=2, sticky=W+E)
        self.prevBtn = Button(self.ctrPanel, text='<< Prev', width=10, command=self.previous_image)
        self.prevBtn.pack(side=LEFT, padx=5, pady=3)
        self.nextBtn = Button(self.ctrPanel, text='Next >>', width=10, command=self.next_image)
        self.nextBtn.pack(side=LEFT, padx=5, pady=3)
        self.progLabel = Label(self.ctrPanel, text="Progress:     /    ")
        self.progLabel.pack(side=LEFT, padx=5)
        self.tmpLabel = Label(self.ctrPanel, text="Go to Image No.")
        self.tmpLabel.pack(side=LEFT, padx=5)
        self.idxEntry = Entry(self.ctrPanel, width=5)
        self.idxEntry.pack(side=LEFT)
        self.goBtn = Button(self.ctrPanel, text='Go', command=self.goto_image)
        self.goBtn.pack(side=LEFT)

        # example pannel for illustration
        self.egPanel = Frame(self.frame, border=10)
        self.egPanel.grid(row=1, column=0, rowspan=5, sticky=N)
        self.tmpLabel2 = Label(self.egPanel, text="Examples:")
        self.tmpLabel2.pack(side=TOP, pady=5)
        self.egLabels = []
        for _ in range(3):
            self.egLabels.append(Label(self.egPanel))
            self.egLabels[-1].pack(side=TOP)

        # display mouse position
        self.disp = Label(self.ctrPanel, text='')
        self.disp.pack(side=RIGHT)

        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(4, weight=1)

    def load_dir_dialog(self):
        """Open a directory browsing dialog to select a dataset within ./Images to annotate"""
        dirpath = filedialog.askdirectory()
        if dirpath:
            # Make dirpath relative to images directory
            subdir_path = Path(dirpath)
            if IMAGES_ROOT not in subdir_path.parents:
                tkMessageBox.showerror(
                    "Error!", message="The directory should be within {0}".format(IMAGES_ROOT))
                return

            self.entry.delete(0, END)
            self.entry.insert(0, str(subdir_path.relative_to(IMAGES_ROOT)))
            self.load_dir()

    def load_dir(self, dbg=False):
        """Load annotation dataset in selected sub directory"""
        if not dbg:
            try:
                subdir = self.entry.get()
                self.parent.focus()
                self.category = subdir
            except ValueError:
                tkMessageBox.showerror("Error!", message="The folder should be numbers")
                return
        if not os.path.isdir(os.path.join(IMAGES_ROOT, self.category)):
            tkMessageBox.showerror("Error!", message="The specified dir doesn't exist!")
            return
        # get image list
        self.imageDir = os.path.join(IMAGES_ROOT, self.category)
        self.imageList = [file
                          for imageType in SUPPORTED_IMAGE_TYPES
                          for file in glob.glob(os.path.join(self.imageDir, imageType))]
        if len(self.imageList) == 0:
            tkMessageBox.showerror(
                "Error!", message="No {0} images found in the specified dir!".format(SUPPORTED_IMAGE_TYPES))
            return

        # default to the 1st image in the collection
        self.cur = 1
        self.total = len(self.imageList)

        # set up output dir
        if not os.path.exists('./Labels'):
            os.mkdir('./Labels')
        self.outDir = os.path.join(r'./Labels', '%s' % (self.category))
        if not os.path.exists(self.outDir):
            os.mkdir(self.outDir)
        self.load_image()
        print('%d images loaded from %s' % (self.total, self.category))

    def load_image(self):
        """Load the current image into the canvas and render any existing labels"""
        # load image
        imagepath = self.imageList[self.cur - 1]
        self.img = PImage.open(imagepath)
        self.curimg_w, self.curimg_h = self.img.size
        self.tkimg = ImageTk.PhotoImage(self.img)
        #self.tkimg = self.tkimg._PhotoImage__photo.zoom(2)
        self.mainPanel.config(width=max(self.tkimg.width(), 400),
                              height=max(self.tkimg.height(), 400))
        self.mainPanel.create_image(0, 0, image=self.tkimg, anchor=NW, tags="IMG")
        self.progLabel.config(text="%04d/%04d" % (self.cur, self.total))

        # load labels
        self.clear_all_bbox()
        # self.imagename = os.path.split(imagepath)[-1].split('.')[0]
        self.imagename = os.path.splitext(os.path.basename(imagepath))[0]
        labelname = self.imagename + '.txt'
        self.labelfilename = os.path.join(self.outDir, labelname)
        if os.path.exists(self.labelfilename):
            with open(self.labelfilename) as label_file:
                for line in label_file:
                    yolo_data = line.strip().split()
                    tl_br_bbox = yolo_bbox_to_tl_br_bbox([float(data) for data in yolo_data[1:]])
                    self.bboxList.append(tl_br_bbox)
                    self.bboxListCls.append(yolo_data[0])

                    abs_bbox = rel_bbox_to_abs_bbox(tl_br_bbox,
                                                    (self.tkimg.width(), self.tkimg.height()))
                    tmpId = self.mainPanel.create_rectangle(abs_bbox[0], abs_bbox[1],
                                                            abs_bbox[2], abs_bbox[3],
                                                            width=2,
                                                            outline=COLOURS[int(yolo_data[0])])
                    self.bboxIdList.append(tmpId)
                    self.listbox.insert(END, '(%.2f, %.2f) -> (%.2f, %.2f) -> (%s)' %
                                        (tl_br_bbox[0], tl_br_bbox[1],
                                         tl_br_bbox[2], tl_br_bbox[3],
                                         CLASSES[int(yolo_data[0])]))
                    self.listbox.itemconfig(len(self.bboxIdList) - 1, fg=COLOURS[int(yolo_data[0])])

    def resize_image(self, event):
        """Resize the current image to fit the canvas"""
        if self.tkimg:
            size = (event.width, event.height)
            resized = self.img.resize(size, PImage.ANTIALIAS)
            self.tkimg = ImageTk.PhotoImage(resized)
            self.mainPanel.delete("IMG")
            self.mainPanel.create_image(0, 0, image=self.tkimg, anchor=NW, tags="IMG")
            self.bboxIdList.clear()
            for tl_br_bbox, bboxcls in zip(self.bboxList, self.bboxListCls):
                abs_bbox = rel_bbox_to_abs_bbox(tl_br_bbox,
                                                (self.tkimg.width(), self.tkimg.height()))
                tmpId = self.mainPanel.create_rectangle(abs_bbox[0], abs_bbox[1],
                                                        abs_bbox[2], abs_bbox[3],
                                                        width=2,
                                                        outline=COLOURS[int(bboxcls)])
                self.bboxIdList.append(tmpId)

    def save_image_labels(self):
        """Save labels for current image to disk"""
        with open(self.labelfilename, 'w') as f:
            for tl_br_bbox, bboxcls in zip(self.bboxList, self.bboxListCls):
                yolo_bbox = tl_br_bbox_to_yolo_bbox(tl_br_bbox)
                f.write(str(bboxcls) + " " + " ".join([str(a) for a in yolo_bbox]) + '\n')
        print('Image No. %d saved' % (self.cur))

    def mouse_click(self, event):
        """On mouse click event finalise and save bounding box"""
        if self.tkimg:
            if self.STATE['click'] == 0:
                self.STATE['x'], self.STATE['y'] = event.x, event.y
            else:
                tl_x = min(self.STATE['x'], event.x)/self.tkimg.width()
                br_x = max(self.STATE['x'], event.x)/self.tkimg.width()
                tl_y = min(self.STATE['y'], event.y)/self.tkimg.height()
                br_y = max(self.STATE['y'], event.y)/self.tkimg.height()
                self.bboxList.append((tl_x, tl_y, br_x, br_y))
                self.bboxListCls.append(self.cur_cls_id)
                self.bboxIdList.append(self.bboxId)
                self.bboxId = None
                self.listbox.insert(END, '(%.2f, %.2f) -> (%.2f, %.2f) -> (%s)' %
                                    (tl_x, tl_y, br_x, br_y, CLASSES[self.cur_cls_id]))
                self.listbox.itemconfig(len(self.bboxIdList) - 1, fg=COLOURS[self.cur_cls_id])
            self.STATE['click'] = 1 - self.STATE['click']

    def mouse_move(self, event):
        """On mouse move event continually update shape of bounding box"""
        if self.tkimg:
            self.disp.config(text='x: %.2f, y: %.2f' %
                             (event.x/self.tkimg.width(), event.y/self.tkimg.height()))
            if self.tkimg:
                if self.hl:
                    self.mainPanel.delete(self.hl)
                self.hl = self.mainPanel.create_line(
                    0, event.y, self.tkimg.width(), event.y, width=2)
                if self.vl:
                    self.mainPanel.delete(self.vl)
                self.vl = self.mainPanel.create_line(
                    event.x, 0, event.x, self.tkimg.height(), width=2)
            if self.STATE['click'] == 1:
                if self.bboxId:
                    self.mainPanel.delete(self.bboxId)
                self.bboxId = self.mainPanel.create_rectangle(self.STATE['x'], self.STATE['y'],
                                                              event.x, event.y,
                                                              width=2,
                                                              outline=COLOURS[self.cur_cls_id])

    def cancel_bbox(self, event):
        """On cancel bbox event (HIT ESCAPE DURING SELECTION) reset active selection bounding box"""
        if self.STATE['click'] == 1:
            if self.bboxId:
                self.mainPanel.delete(self.bboxId)
                self.bboxId = None
                self.STATE['click'] = 0

    def delete_bbox(self):
        """On delete bounding box event (DELETE BUTTON CLICK), delete selected bounding box"""
        sel = self.listbox.curselection()
        if len(sel) != 1:
            return
        idx = int(sel[0])
        self.mainPanel.delete(self.bboxIdList[idx])
        self.bboxIdList.pop(idx)
        self.bboxList.pop(idx)
        self.bboxListCls.pop(idx)
        self.listbox.delete(idx)

    def clear_all_bbox(self):
        """On clear all bounding box event (CLEAR ALL BUTTON CLICK), remove ALL bounding boxes"""
        for idx in range(len(self.bboxIdList)):
            self.mainPanel.delete(self.bboxIdList[idx])
        self.listbox.delete(0, len(self.bboxList))
        self.bboxIdList = []
        self.bboxList = []
        self.bboxListCls = []

    def previous_image(self, event=None):
        """Load previous image in annotation queue"""
        self.save_image_labels()
        if self.cur > 1:
            self.cur -= 1
            self.load_image()
        else:
            tkMessageBox.showerror("Information!", message="This is first image")

    def next_image(self, event=None):
        """Load next image in annotation queue"""
        self.save_image_labels()
        if self.cur < self.total:
            self.cur += 1
            self.load_image()
        else:
            tkMessageBox.showerror("Information!", message="All images annotated")

    def goto_image(self):
        """Go to specific image in annotation queue"""
        idx = int(self.idxEntry.get())
        if 1 <= idx <= self.total:
            self.save_image_labels()
            self.cur = idx
            self.load_image()

    def change_dropdown(self, *args):
        """Update currently selected annotation class from dropdown selection"""
        cur_cls = self.tkvar.get()
        self.cur_cls_id = CLASSES.index(cur_cls)


if __name__ == '__main__':
    TK_ROOT = Tk()
    LABEL_TOOL = LabelTool(TK_ROOT)
    TK_ROOT.resizable(width=True, height=True)
    TK_ROOT.mainloop()
