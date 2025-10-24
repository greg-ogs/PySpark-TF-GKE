'''
Created byu greg-ogs
'''
import numpy as np
import os
import time
import tensorflow as tf
import matplotlib.pyplot as plt
from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense
import PIL.Image as im
from tqdm import tqdm

class ManualImageChecker:
    def __init__(self, image_path: str = "/app/infra/local/mysql-database/datasets/image-datasets/laser-spots"):
        self.model = tf.keras.models.load_model("./tf-model/150-320-by-256-B1-model.keras")
        self.model.summary()
        self.images_path = image_path
        self.image_path = None

    def predict(self):
        image = im.open(self.image_path).convert("RGB").resize((320, 256))
        image_array = np.array(image) / 255.0
        img_array = tf.keras.utils.img_to_array(image_array)
        img_arr = tf.expand_dims(img_array, 0)
        prediction = self.model.predict(img_arr, verbose=0)
        return prediction

    def img_to_plot(self, predictions, fig, ax):
        x = predictions[0][0]
        y = predictions[0][1]
        image_to_plot = im.open(self.image_path).convert("RGB")
        ax.clear()
        ax.imshow(image_to_plot, origin='lower')
        ax.plot(x, y, marker='o', markersize=15, color='red')
        ax.set_title(f"Superpixels -- CNN-- Prediction for {self.image_path.split('/')[-1]}")
        ax.set_xlabel("pixels")
        ax.set_ylabel("pixels")
        ax.axis("on")
        # fig.show()
        fig.savefig(f"./tf-model/plots/{self.image_path.split('/')[-1]}")
        
    def main(self):

        plt.rcParams.update({'font.size': 30})
        fig, ax = plt.subplots(figsize=(24, 20))
        for filename in tqdm(os.listdir(self.images_path)):
            if filename.lower().endswith('.png'):
                self.image_path = os.path.join(self.images_path, filename)
                predictions = self.predict()
                self.img_to_plot(predictions, fig, ax)
                time.sleep(1)

if __name__ == "__main__":
    os.makedirs("./tf-model/plots/", exist_ok=True)
    img_checker_instance = ManualImageChecker()
    img_checker_instance.main()