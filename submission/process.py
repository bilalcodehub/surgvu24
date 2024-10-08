# AUTOGENERATED! DO NOT EDIT! File to edit: make_process.ipynb.

# %% auto 0
__all__ = ['logger', 'execute_in_docker', 'get_image', 'get_label', 'VideoLoader', 'UniqueVideoValidator', 'SurgVU_classify']

# %% make_process.ipynb 1
from fastai.vision.all import *
import SimpleITK
from pandas import DataFrame
from scipy.ndimage import center_of_mass, label
from pathlib import Path
from evalutils import ClassificationAlgorithm
from evalutils.validators import (
    UniquePathIndicesValidator,
    DataFrameValidator,
)
from typing import (Tuple)
from evalutils.exceptions import ValidationError
import random
from typing import Dict
import json
import subprocess
import shutil
import logging
from skimage.measure import label, regionprops, find_contours
import segmentation_models_pytorch as smp
import cv2

# %% make_process.ipynb 2
# Set up logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# %% make_process.ipynb 3
execute_in_docker = True

# %% make_process.ipynb 4
def get_image(r): 
    """
    Constructs the full image path for a given row in the DataFrame.
    
    Args:
        r (pd.Series): A row from the DataFrame.
    
    Returns:
        str: Full path to the image file.
    """
    return str(dataroot_path / 'frames' / f"{r['filename']}.jpg")

def get_label(r): 
    """
    Retrieves the task label from a given row in the DataFrame.
    
    Args:
        r (pd.Series): A row from the DataFrame.
    
    Returns:
        str: The task label.
    """
    return r['task_label']

# %% make_process.ipynb 5
class VideoLoader():
    def load(self, *, fname):
        path = Path(fname)
        if not path.is_file():
            raise IOError(
                f"Could not load {fname} using {self.__class__.__qualname__}."
            )
            #cap = cv2.VideoCapture(str(fname))
        #return [{"video": cap, "path": fname}]
        return [{"path": fname}]

# only path valid
    def hash_video(self, input_video):
        pass

# %% make_process.ipynb 6
class UniqueVideoValidator(DataFrameValidator):
    """
    Validates that each video in the set is unique
    """

    def validate(self, *, df: DataFrame):
        try:
            hashes = df["video"]
        except KeyError:
            raise ValidationError("Column `video` not found in DataFrame.")

        if len(set(hashes)) != len(hashes):
            raise ValidationError(
                "The videos are not unique, please submit a unique video for "
                "each case."
            )

# %% make_process.ipynb 7
class SurgVU_classify(ClassificationAlgorithm):
    def __init__(self):
        super().__init__(
            index_key='input_video',
            file_loaders={'input_video': VideoLoader()},
            input_path=Path("/input/") if execute_in_docker else Path("./test/"),
            output_file=Path("/output/surgical-step-classification.json") if execute_in_docker else Path(
                "./output/surgical-step-classification.json"),
            validators=dict(
                input_video=(
                    # UniqueVideoValidator(),
                    UniquePathIndicesValidator(),
                )
            ),
        )

        # Log the initialization process
        logger.info('Initializing the model and setting up configurations.')

        # Set CPU flag
        self.cpu = False
        self.window_size = 8
        models_path = Path('/opt/algorithm/models/') if execute_in_docker else Path("./models/")

        # Load the task models
        try:
            logger.info(f'Loading models from the {models_path} directory.')
            self.learners = [load_learner(m, cpu=self.cpu) for m in models_path.ls() if m.suffix == '.pkl']
            logger.info(f'{len(self.learners)} models are located & successfully loaded.')
        except Exception as e:
            logger.error(f'Error loading models: {e}')
            raise

        # Verify that all learners have the same vocabulary
        try:
            logger.info('Verifying that all learners have the same vocabulary.')
            # Retrieve the vocab from each learner
            vocabs = [learner.dls.vocab for learner in self.learners]
            # Use the vocab from the first learner as reference
            reference_vocab = vocabs[0]
            for idx, vocab in enumerate(vocabs[1:], start=1):
                if vocab != reference_vocab:
                    logger.error(f'Vocabulary mismatch between learner 0 and learner {idx}')
                    # Optionally, you can log the differences
                    diff = set(vocab) ^ set(reference_vocab)
                    logger.error(f'Differences in vocabularies: {diff}')
                    raise ValueError('Learner vocabularies do not match!')
            logger.info('All learners have the same vocabulary.')
            self.vocab = reference_vocab  # Store the common vocabulary
        except Exception as e:
            logger.error(f'Error during vocabulary verification: {e}')
            raise

        # Initialize the surgical step list
        self.step_list = [
            "range_of_motion",
            "rectal_artery_vein",
            "retraction_collision_avoidance",
            "skills_application",
            "suspensory_ligaments",
            "suturing",
            "uterine_horn",
            "other"
        ]

        logger.info('Surgical step list initialized successfully.')
        
        # Verify that step_list and vocab contain the same elements
        try:
            if set(self.step_list) != set(self.vocab):
                logger.error('Mismatch between elements in step_list and learners\' vocabulary.')
                missing_in_vocab = set(self.step_list) - set(self.vocab)
                missing_in_step_list = set(self.vocab) - set(self.step_list)
                if missing_in_vocab:
                    logger.error(f'Elements in step_list not in vocab: {missing_in_vocab}')
                if missing_in_step_list:
                    logger.error(f'Elements in vocab not in step_list: {missing_in_step_list}')
                raise ValueError('step_list does not contain the same elements as learners\' vocabulary.')
            else:
                logger.info('step_list contains the same elements as the learners\' vocabulary.')
        except Exception as e:
            logger.error(f'Error during step_list verification: {e}')
            raise


    def dummy_step_prediction_model(self):
        random_step_prediction = random.randint(0, len(self.step_list)-1)
        return random_step_prediction
    
    
    def step_predict_json_sample(self):
        single_output_dict = {"frame_nr": 1, "surgical_step": None}
        return single_output_dict


    def process_case(self, *, idx, case):

        # Input video would return the collection of all frames (cap object)
        input_video_file_path = case #VideoLoader.load(case)
        # Detect and score candidates
        scored_candidates = self.predict(case.path) #video file > load evalutils.py

        # return
        # Write resulting candidates to result.json for this case
        return scored_candidates


    def save(self):
        try:
            with open(str(self._output_file), "w") as f:
                json.dump(self._case_results[0], f)
            logger.info(f'Predictions saved to {str(self._output_file)} successfully.')
        except Exception as e:
            logger.error(f'Failed to save predictions to {str(self._output_file)}. Error: {e}')
            raise

    def split_video(self, video_path: Path):
        # Ensure the input is a Path object and the file exists
        if not isinstance(video_path, Path):
            raise TypeError("video_path must be a Path object.")
        if not video_path.is_file():
            raise FileNotFoundError(f"The file {video_path} does not exist.")

        # Create the frames directory in the parent of the parent directory
        frames_dir = video_path.parent.parent / "frames" / video_path.stem

        # Delete the output directory if it already exists
        if frames_dir.exists() and frames_dir.is_dir():
            shutil.rmtree(frames_dir)

        # Create the output directory
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Prepare the ffmpeg command
        output_pattern = frames_dir / "%d.jpg"
        ffmpeg_command = [
            "ffmpeg",
            "-i", str(video_path),
            "-start_number", "0",     # Start numbering from 0
            "-r", "1",
            str(output_pattern)
        ]

        # Run the ffmpeg command
        subprocess.run(ffmpeg_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        return frames_dir
    

    def get_sorted_image_files(self, frames_dir: Path):
        # Get all image files in the directory
        image_files = get_image_files(frames_dir)

        # Sort files based on the integer value of the filename
        sorted_files = sorted(image_files, key=lambda f: int(''.join(filter(str.isdigit, f.stem))))

        return L(sorted_files)

    def smooth_predictions(self, predicted_classes: List[str], window_size: int = 1) -> List[str]:
        """
        Smooths the predicted class labels by exploring the neighboring frames.

        Args:
            predicted_classes (List[str]): The list of predicted class labels per frame.
            window_size (int): Number of neighboring frames to consider on each side for smoothing.

        Returns:
            List[str]: The smoothed list of predicted class labels.
        """
        if not predicted_classes:
            return []

        num_frames = len(predicted_classes)
        smoothed_predictions = []

        for i in range(num_frames):
            # Define the window boundaries
            start_idx = max(0, i - window_size)
            end_idx = min(num_frames - 1, i + window_size)

            # Extract the neighborhood labels
            neighborhood = predicted_classes[start_idx:end_idx + 1]

            # Count the frequency of each label in the neighborhood
            label_counts = {}
            for label in neighborhood:
                label_counts[label] = label_counts.get(label, 0) + 1

            # Identify the most common label(s)
            max_count = max(label_counts.values())
            common_labels = [label for label, count in label_counts.items() if count == max_count]

            # Resolve ties by retaining the current frame's label
            if len(common_labels) == 1:
                most_common_label = common_labels[0]
            else:
                most_common_label = predicted_classes[i]

            smoothed_predictions.append(most_common_label)

        return smoothed_predictions

    def predict(self, fname) -> Dict:
        """
        Inputs:
        fname -> video file path

        Output:
        tools -> list of prediction dictionaries (per frame) in the correct format as described in documentation 
        """
        logger.info(f'Starting prediction process for video: {str(fname)}')

        # Step 1: Split the video into frames
        frames_dir = self.split_video(fname)
        logger.info(f'Frame extraction completed for video: {str(fname)}. Frames stored in directory: {frames_dir}')

        # Step 2: Get sorted list of image files
        image_files = self.get_sorted_image_files(frames_dir)
        image_files = [str(image_file) for image_file in image_files]
        num_frames = len(image_files)
        logger.info(f'{num_frames} frames identified for processing.')

        # Step 3: Perform inference with ensemble
        logger.info('Performing inference with ensemble models...')
        all_raw_preds = []
        test_items = []

        # Collect predictions from each model in the ensemble
        for idx, learner in enumerate(self.learners):
            # Create a test_dl to apply the requisite transforms
            test_dl = learner.dls.test_dl(image_files, bs=64, num_workers=0)

            # For the first learner, store test_items
            if idx == 0:
                test_items = [str(item) for item in test_dl.items]
                logger.info('Stored test items from the first learner for validation.')
            else:
                # For other learners, compare test_dl.items to test_items
                current_items = [str(item) for item in test_dl.items]
                if current_items != test_items:
                    logger.error(f"Test items in learner {idx} do not match the first learner.")
                    # Optionally, log the differences
                    differences = [(i, item1, item2) for i, (item1, item2) in enumerate(zip(current_items, test_items)) if item1 != item2]
                    logger.error(f"Differences found in test items: {differences}")
                    raise ValueError(f"Test items in learner {idx} do not match the first learner.")
                else:
                    logger.info(f'Test items in learner {idx} match the first learner.')

            # Get predictions from the current learner
            raw_preds, _ = learner.get_preds(dl=test_dl)
            all_raw_preds.append(raw_preds)

        # Average the predictions across all models
        avg_raw_preds = torch.stack(all_raw_preds).mean(0)
        logger.info('Inference completed successfully using ensemble models.')

        # Step 4: Decode predictions to class names
        softmax_preds = avg_raw_preds.softmax(dim=1)
        argmax_preds = softmax_preds.argmax(dim=1)
        predicted_classes = [self.vocab[pred] for pred in argmax_preds]

        # --- Added Step: Smooth Predictions ---
        logger.info('Applying smoothing to predictions...')
        # Assuming `smooth_predictions_with_neighbors` is a method of the class
        smoothed_pred_classes = self.smooth_predictions(predicted_classes, window_size=self.window_size)
        logger.info('Smoothing applied successfully.')
        # --- End of Added Step ---

        # Step 5: Generate output JSON
        logger.info('Formatting predictions for JSON output...')
        # Create a mapping from class names to indices in step_list
        step_list_index_map = {name: idx for idx, name in enumerate(self.step_list)}
        all_frames_predicted_outputs = []
        for img_path, class_name in zip(test_items, smoothed_pred_classes):  # Use smoothed_pred_classes instead of predicted_classes
            img_path = Path(img_path)
            frame_dict = self.step_predict_json_sample()
            frame_dict['frame_nr'] = int(img_path.stem)

            # Map the predicted class name to the corresponding index in self.step_list
            frame_dict["surgical_step"] = step_list_index_map.get(class_name, -1)

            all_frames_predicted_outputs.append(frame_dict)

        steps = all_frames_predicted_outputs
        logger.info(f'Prediction process completed for video: {str(fname)}. Results ready for output.')

        return steps
    
if __name__ == "__main__":
    SurgVU_classify().process()
